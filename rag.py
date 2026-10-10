import os
import json
import sqlite3
import math
from pathlib import Path
from ollama import AsyncClient
from security import validate_path

EMBED_MODEL = "nomic-embed-text"
EMBED_BATCH_SIZE = 32
MAX_INDEX_FILE_SIZE = 5 * 1024 * 1024 # 5 MB

class RagIndex:
    def __init__(self, db_path: str, client=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.client = client

    def get_client(self):
        if self.client is None:
            self.client = AsyncClient()
        return self.client

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    relative_path TEXT,
                    chunk_index INTEGER,
                    chunk_text TEXT,
                    embedding TEXT,
                    last_modified REAL,
                    file_size INTEGER
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_filename ON document_chunks(filename)')
            
    async def check_model(self):
        try:
            models = await self.get_client().list()
            model_names = [m.model for m in models.models] if hasattr(models, 'models') else [m['name'] for m in models.get('models', [])]
            return any(name.startswith(EMBED_MODEL) for name in model_names)
        except Exception:
            return False

    def chunk_text(self, text: str, target_size=1000, overlap=200):
        if not text.strip():
            return []
            
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for p in paragraphs:
            if not p.strip():
                continue
                
            if len(p) > target_size:
                lines = p.split('\n')
                for line in lines:
                    if len(line) > target_size:
                        for i in range(0, len(line), target_size - overlap):
                            part = line[i:i + target_size]
                            if current_chunk and len(current_chunk) + len(part) > target_size:
                                chunks.append(current_chunk.strip())
                                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                                current_chunk = overlap_text + "\n" + part
                            else:
                                current_chunk += part + "\n"
                    else:
                        if current_chunk and len(current_chunk) + len(line) > target_size:
                            chunks.append(current_chunk.strip())
                            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                            current_chunk = overlap_text + "\n" + line
                        else:
                            current_chunk += line + "\n"
            else:
                if current_chunk and len(current_chunk) + len(p) > target_size:
                    chunks.append(current_chunk.strip())
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    current_chunk = overlap_text + "\n\n" + p
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + p
                    else:
                        current_chunk = p
                        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        return chunks

    async def update_index(self, sandbox_root: str) -> str:
        if not await self.check_model():
            return f"Error: Embedding model '{EMBED_MODEL}' is missing. Please run 'ollama pull {EMBED_MODEL}'."
            
        try:
            root_path = validate_path(sandbox_root, expected_type="dir")
        except Exception as e:
            return f"Error validating sandbox root: {e}"
            
        allowed_exts = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".html", ".css"}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename, last_modified, file_size FROM document_chunks")
            db_files = {}
            for row in cursor.fetchall():
                db_files[row[0]] = {'mtime': row[1], 'size': row[2]}
                
        current_files = {}
        skipped_count = 0
        
        for root, dirs, files in os.walk(root_path):
            filtered_dirs = []
            for d in dirs:
                if d.startswith('.'):
                    continue
                d_path = Path(root) / d
                if d_path.is_symlink() or (hasattr(d_path, 'is_junction') and d_path.is_junction()):
                    continue
                filtered_dirs.append(d)
            dirs[:] = filtered_dirs
            
            for name in files:
                if name.startswith('.'):
                    continue
                path = Path(root) / name
                if path.suffix.lower() not in allowed_exts:
                    skipped_count += 1
                    continue
                if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                    skipped_count += 1
                    continue
                try:
                    safe_path = validate_path(str(path), expected_type="file")
                except Exception:
                    skipped_count += 1
                    continue
                rel_path = safe_path.relative_to(root_path).as_posix()
                current_files[rel_path] = safe_path

        to_delete = []
        to_index = []
        
        for rel_path, safe_path in current_files.items():
            try:
                stat = safe_path.stat()
                mtime = stat.st_mtime
                size = stat.st_size
                if rel_path in db_files:
                    if db_files[rel_path]['mtime'] != mtime or db_files[rel_path]['size'] != size:
                        to_delete.append(rel_path)
                        to_index.append((rel_path, safe_path, mtime, size))
                else:
                    to_index.append((rel_path, safe_path, mtime, size))
            except Exception:
                skipped_count += 1
                
        for rel_path in db_files:
            if rel_path not in current_files:
                to_delete.append(rel_path)
                
        pure_deletes = [p for p in set(to_delete) if p not in [x[0] for x in to_index]]
        with sqlite3.connect(self.db_path) as conn:
            for rel_path in pure_deletes:
                conn.execute("DELETE FROM document_chunks WHERE filename = ?", (rel_path,))
                
        indexed_count = 0
        for rel_path, safe_path, mtime, size in to_index:
            if size > MAX_INDEX_FILE_SIZE:
                skipped_count += 1
                continue
            try:
                with open(safe_path, "rb") as f:
                    content_bytes = f.read(MAX_INDEX_FILE_SIZE + 1)
                    if len(content_bytes) > MAX_INDEX_FILE_SIZE:
                        skipped_count += 1
                        continue
                    if b'\x00' in content_bytes:
                        skipped_count += 1
                        continue
                text = content_bytes.decode('utf-8', errors='replace')
                chunks = self.chunk_text(text)
                
                all_embeddings = []
                for i in range(0, len(chunks), EMBED_BATCH_SIZE):
                    batch = chunks[i:i + EMBED_BATCH_SIZE]
                    resp = await self.get_client().embed(model=EMBED_MODEL, input=batch)
                    if 'embeddings' not in resp or len(resp['embeddings']) != len(batch):
                        raise ValueError("Embedding count mismatch")
                    # Fixed 768 dimension check because Milestone 3 strictly assumes nomic-embed-text
                    if any(len(emb) != 768 for emb in resp['embeddings']):
                        raise ValueError("Embedding dimension mismatch")
                    all_embeddings.extend(resp['embeddings'])
                    
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM document_chunks WHERE filename = ?", (rel_path,))
                    for j, (chunk, emb) in enumerate(zip(chunks, all_embeddings)):
                        conn.execute('''
                            INSERT INTO document_chunks 
                            (filename, relative_path, chunk_index, chunk_text, embedding, last_modified, file_size)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (rel_path, rel_path, j, chunk, json.dumps(emb), mtime, size))
                indexed_count += 1
            except Exception:
                skipped_count += 1

        return f"Index updated: {indexed_count} files newly indexed, {skipped_count} files skipped, {len(set(to_delete))} old files removed."


    def cosine_similarity(self, a, b):
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    async def search(self, query: str, top_k=5) -> str:
        if not await self.check_model():
            return f"Error: Embedding model '{EMBED_MODEL}' is missing. Please run 'ollama pull {EMBED_MODEL}'."
            
        try:
            resp = await self.get_client().embed(model=EMBED_MODEL, input=query)
            query_emb = resp['embeddings'][0]
            
            results = []
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT filename, chunk_index, chunk_text, embedding FROM document_chunks")
                for row in cursor.fetchall():
                    filename, chunk_idx, text, emb_json = row
                    emb = json.loads(emb_json)
                    sim = self.cosine_similarity(query_emb, emb)
                    results.append((sim, filename, chunk_idx, text))
            
            results.sort(key=lambda x: x[0], reverse=True)
            top_results = results[:top_k]
            
            if not top_results:
                return "I couldn't find enough evidence in the indexed documents."
                
            out_parts = []
            total_chars = 0
            
            for sim, filename, chunk_idx, text in top_results:
                block = f"[File: {filename}]\n[Path: {filename}]\n[Chunk: {chunk_idx}]\n[Score: {sim:.2f}]\n{text}\n"
                if total_chars + len(block) > 15000:
                    out_parts.append("\n[...TRUNCATED: Context limit reached]")
                    break
                out_parts.append(block)
                total_chars += len(block)
                
            return "\n".join(out_parts)
            
        except Exception as e:
            return f"Error during search: {e}"
