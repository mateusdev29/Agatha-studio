"""Registro único da navegação lateral (grupos separados por linha fina na sidebar)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    slug: str
    label: str
    icon: str
    path: str


NAV_GROUPS: list[list[NavItem]] = [
    [
        NavItem("visao-geral", "Visão Geral", "home", "/"),
        NavItem("dashboard", "Dashboard", "chart", "/dashboard"),
    ],
    [
        NavItem("agenda", "Agenda", "calendar", "/agenda"),
        NavItem("projetos", "Projetos", "layers", "/projetos"),
        NavItem("orcamentos", "Orçamentos", "file", "/orcamentos"),
        NavItem("clientes", "Clientes", "users", "/clientes"),
    ],
    [
        NavItem("anamnese", "Anamnese", "clipboard", "/anamnese"),
        NavItem("estoque", "Estoque", "box", "/estoque"),
        NavItem("financeiro", "Financeiro", "wallet", "/financeiro"),
    ],
    [
        NavItem("satisfacao", "Satisfação", "star", "/satisfacao"),
        NavItem("preferencias", "Preferências Corporais", "body", "/preferencias-corporais"),
    ],
    [
        NavItem("configuracoes", "Configurações", "settings", "/configuracoes"),
    ],
]


def all_items() -> list[NavItem]:
    return [item for group in NAV_GROUPS for item in group]



def is_active(item: NavItem, current_path: str) -> bool:
    if item.path == "/":
        return current_path == "/"
    return current_path == item.path or current_path.startswith(item.path + "/")
