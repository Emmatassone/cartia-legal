import os

# Los settings se instancian al importar los modulos, asi que los defaults tienen que
# existir antes de que pytest colecte los tests.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://cartia:cartia@localhost:5432/cartia")
os.environ.setdefault("JWT_SECRET", "test-secret-de-al-menos-32-caracteres-1234")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
