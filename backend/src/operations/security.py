import re
from dataclasses import dataclass

IDENTITY_RE=re.compile(r"^[A-Za-z0-9_.@:+-]{1,160}$")
ROLE_ORDER={"viewer":1,"operator":2,"admin":3}
PUBLIC_PATHS={"/health","/health/live","/api/v1/health"}

@dataclass(frozen=True)
class Principal:
    actor: str
    roles: frozenset[str]
    auth_mode: str

    @property
    def role_level(self):
        return max((ROLE_ORDER.get(role,0) for role in self.roles),default=0)

@dataclass(frozen=True)
class Decision:
    allowed: bool
    status_code: int
    code: str | None
    principal: Principal | None
    required_role: str | None

def required_role(method,path):
    if path in PUBLIC_PATHS:
        return None
    if path.startswith("/api/v1/operations/audit"):
        return "admin"
    if method.upper() in {"GET","HEAD","OPTIONS"}:
        return "viewer"
    return "operator"

def principal_from_headers(settings,headers):
    if settings.auth_mode=="disabled":
        return Principal("local-development",frozenset({"viewer","operator","admin"}),"disabled")
    actor=(headers.get(settings.auth_user_header) or "").strip()
    if not IDENTITY_RE.fullmatch(actor):
        return None
    raw=(headers.get(settings.auth_roles_header) or "")
    roles=frozenset(part.strip().lower() for part in raw.split(",") if part.strip().lower() in ROLE_ORDER)
    if not roles:
        return None
    return Principal(actor,roles,"proxy_headers")

def authorize(settings,method,path,headers):
    role=required_role(method,path)
    if role is None:
        return Decision(True,200,None,Principal("public",frozenset(),"public"),None)
    principal=principal_from_headers(settings,headers)
    if principal is None:
        return Decision(False,401,"authentication_required",None,role)
    if principal.role_level<ROLE_ORDER[role]:
        return Decision(False,403,"insufficient_role",principal,role)
    return Decision(True,200,None,principal,role)

def security_status(settings):
    return {
        "auth_mode":settings.auth_mode,
        "credentials_stored":False,
        "identity_source":"trusted_proxy_headers" if settings.auth_mode=="proxy_headers" else "local_development",
        "roles":["viewer","operator","admin"],
        "production_gate":True,
    }
