from threading import Lock
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def encode(self, texts: list[str]) -> list[list[float]]:
        ...


class LocalEmbeddingProvider:
    def __init__(self, model_name: str, dimension: int = 512):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._load_lock = Lock()

    @property
    def ready(self) -> bool:
        return self._model is not None

    def warm_up(self) -> None:
        self.encode(["智能客服知识检索预热"])

    def _load(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self.model_name)
                    actual_dimension = model.get_sentence_embedding_dimension()
                    if actual_dimension != self.dimension:
                        raise ValueError(
                            f"Embedding dimension mismatch: configured {self.dimension}, model returned {actual_dimension}"
                        )
                    self._model = model
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [[float(value) for value in vector] for vector in vectors]
