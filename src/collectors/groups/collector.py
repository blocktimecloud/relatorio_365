from collectors.base import BaseCollector


class GroupsCollector(BaseCollector):
    """
    Coleta todos os grupos e seus membros.
    Permissão necessária: Group.Read.All

    Tipos de grupo identificados pelos campos:
        Lista de distribuição  → mailEnabled=True,  securityEnabled=False, groupTypes=[]
        Segurança              → mailEnabled=False, securityEnabled=True,  groupTypes=[]
        Microsoft 365          → groupTypes=["Unified"]
        Seg. habilitada email  → mailEnabled=True,  securityEnabled=True,  groupTypes=[]
    """

    def collect(self) -> list[dict]:
        data = self._client.get(
            "groups",
            params={
                "$select": "id,displayName,groupTypes,mailEnabled,securityEnabled,mail"
            }
        )
        groups = data.get("value", [])

        # para cada grupo, busca os membros
        for group in groups:
            members = self._client.get(
                f"groups/{group['id']}/members",
                params={"$select": "displayName,mail"}
            )
            group["members"] = members.get("value", [])

        return groups