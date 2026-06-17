import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config.settings import settings


# ── Engine ──────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # testa a conexão antes de usar do pool
    pool_recycle=3600,    # recicla conexões após 1h (evita timeout do MySQL)
    pool_size=5,          # conexões mantidas abertas no pool
    max_overflow=10,      # conexões extras permitidas além do pool_size
    echo=settings.is_development,
)

# ── Session factory ──────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base declarativa ─────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Gerador de sessão ────────────────────────────────────────────────────
def get_db():
    """
    Gerador de sessão para uso no FastAPI (Depends) e no CLI.
    Garante que a sessão seja sempre fechada ao final.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Criação de tabelas ───────────────────────────────────────────────────
def create_tables() -> None:
    """
    Cria todas as tabelas registradas no metadata caso não existam.
    Importa os models aqui para garantir que estejam registrados.
    """
    from customer.orm import CustomerModel  # noqa: F401
    Base.metadata.create_all(bind=engine)


# ── Verificação de conectividade ─────────────────────────────────────────
def check_connection() -> bool:
    """Retorna True se a conexão com o banco estiver funcionando."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Falha na conexão: {e}", file=sys.stderr)
        return False