"""Store and search vectors using PostgreSQL + pgvector."""
from typing import Any
import psycopg
from psycopg.types.json import Jsonb
from .models import Chunk


def _format_vector(vec: list[float]) -> str:
    """Chuyển list[float] thành chuỗi '[x1,x2,...]' để ép kiểu ::vector trong SQL."""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("database_url cannot be empty")
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self.database_url = database_url
        self.dimensions = dimensions

    def create_schema(self) -> None:
        """Create table with vector column and source/page/filter metadata."""
        ddl = f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS document_chunks (
            strategy TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source TEXT NOT NULL,
            page INTEGER NOT NULL,
            text TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            embedding VECTOR({self.dimensions}) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (strategy, chunk_id)
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_strategy_doc
            ON document_chunks (strategy, document_id);

        CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin
            ON document_chunks USING GIN (metadata);
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions and write stable IDs without duplicates."""
        if not strategy:
            raise ValueError("strategy cannot be empty")
        if len(chunks) != len(vectors):
            raise ValueError(f"Mismatch: {len(chunks)} chunks vs {len(vectors)} vectors")
        if not chunks:
            return

        for idx, vec in enumerate(vectors):
            if len(vec) != self.dimensions:
                raise ValueError(
                    f"Vector at index {idx} has {len(vec)} dims, expected {self.dimensions}"
                )

        # Gom danh sách chunk_id mới theo từng document_id để dọn chunk cũ thừa
        doc_to_ids: dict[str, list[str]] = {}
        for chunk in chunks:
            doc_to_ids.setdefault(chunk.document_id, []).append(chunk.chunk_id)

        upsert_sql = """
        INSERT INTO document_chunks (
            strategy, chunk_id, document_id, source, page, text, metadata, embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
        ON CONFLICT (strategy, chunk_id) DO UPDATE SET
            document_id = EXCLUDED.document_id,
            source = EXCLUDED.source,
            page = EXCLUDED.page,
            text = EXCLUDED.text,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            updated_at = NOW();
        """

        delete_obsolete_sql = """
        DELETE FROM document_chunks
        WHERE strategy = %s
          AND document_id = %s
          AND NOT (chunk_id = ANY(%s));
        """

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                for doc_id, valid_ids in doc_to_ids.items():
                    cur.execute(delete_obsolete_sql, (strategy, doc_id, valid_ids))

                rows = [
                    (
                        strategy,
                        c.chunk_id,
                        c.document_id,
                        c.source,
                        c.page,
                        c.text,
                        Jsonb(c.metadata),
                        _format_vector(vec),
                    )
                    for c, vec in zip(chunks, vectors)
                ]
                cur.executemany(upsert_sql, rows)
            conn.commit()

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by cosine distance, return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"query_vector has {len(query_vector)} dims, expected {self.dimensions}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be > 0")

        vec_literal = _format_vector(query_vector)
        params: list[Any] = [vec_literal, strategy]
        filter_clause = ""

        if filters:
            filter_clause = "AND metadata @> %s"
            params.append(Jsonb(filters))

        params.extend([vec_literal, top_k])

        query_sql = f"""
        SELECT
            chunk_id,
            document_id,
            source,
            page,
            text,
            metadata,
            1 - (embedding <=> %s::vector) AS score
        FROM document_chunks
        WHERE strategy = %s
        {filter_clause}
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s;
        """

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query_sql, params)
                rows = cur.fetchall()

        return [
            {
                "chunk_id": r[0],
                "document_id": r[1],
                "source": r[2],
                "page": r[3],
                "text": r[4],
                "metadata": r[5],
                "score": float(r[6]),
            }
            for r in rows
        ]