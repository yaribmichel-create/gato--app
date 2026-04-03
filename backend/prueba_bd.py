from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base

# 1. Le decimos al asistente dónde crear el cuaderno (el archivo .db)
motor = create_engine("sqlite:///./cuaderno_prueba.db")
Base = declarative_base()

# 2. Creamos el "molde" (la tabla) usando código Python normal
class Jugador(Base):
    __tablename__ = "jugadores"
    id = Column(Integer, primary_key=True)
    nombre = Column(String)
    victorias = Column(Integer)

# 3. Le damos la orden final de fabricar el cuaderno con ese molde
Base.metadata.create_all(motor)

print("¡Magia lista! Revisa tu carpeta, debe haber un archivo nuevo.")