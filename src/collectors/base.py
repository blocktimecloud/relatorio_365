from abc import ABC, abstractmethod
from integrations.graph.client import GraphClient


class BaseCollector(ABC):
    def __init__(self, graph_client: GraphClient):
        self._client = graph_client

    @abstractmethod
    def collect(self) -> list[dict]:
        """Busca e retorna os dados da Graph API."""
        ...