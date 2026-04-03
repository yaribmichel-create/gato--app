from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import os
import hashlib # <-- ¡Nuestra licuadora de contraseñas!

# --- FUNCIÓN DE SEGURIDAD ---
def encriptar_password(password: str):
    # Licúa la contraseña y la convierte en un código ilegible
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 1. BASE DE DATOS Y TABLAS
# ==========================================
SQLALCHEMY_DATABASE_URL = "postgresql://admin:password123@localhost:5433/gato_db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Perfil(Base):
    __tablename__ = "perfiles"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    password_hash = Column(String) # <-- ¡NUEVA COLUMNA DE SEGURIDAD!
    victorias = Column(Integer, default=0)

class Partida(Base):
    __tablename__ = "partidas"
    id = Column(Integer, primary_key=True, index=True)
    ganador_id = Column(Integer, ForeignKey("perfiles.id")) 
    perdedor_id = Column(Integer, ForeignKey("perfiles.id")) 

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 2. LÓGICA DEL JUEGO (Se queda igual)
# ==========================================
class GameManager:
    def __init__(self):
        self.conexiones: list[WebSocket] = []
        self.jugadores = {"X": None, "O": None}
        self.nombres = {"X": "Esperando...", "O": "Esperando..."}
        self.tablero = [""] * 9
        self.turno = "X"

    def verificar_ganador(self):
        lineas = [[0,1,2], [3,4,5], [6,7,8], [0,3,6], [1,4,7], [2,5,8], [0,4,8], [2,4,6]]
        for a, b, c in lineas:
            if self.tablero[a] and self.tablero[a] == self.tablero[b] == self.tablero[c]:
                return self.tablero[a]
        if "" not in self.tablero: return "Empate"
        return None

    async def conectar(self, websocket: WebSocket, nombre_usuario: str):
        await websocket.accept()
        self.conexiones.append(websocket)
        if self.jugadores["X"] is None:
            jugador = "X"
            self.jugadores["X"] = websocket
            self.nombres["X"] = nombre_usuario
        elif self.jugadores["O"] is None:
            jugador = "O"
            self.jugadores["O"] = websocket
            self.nombres["O"] = nombre_usuario
        else: jugador = "Espectador"
        
        await websocket.send_json({"tipo": "inicio", "jugador": jugador, "tablero": self.tablero, "turno": self.turno})
        await self.enviar_a_todos({"tipo": "actualizacion_nombres", "nombres": self.nombres})

    def desconectar(self, websocket: WebSocket):
        self.conexiones.remove(websocket)
        if self.jugadores["X"] == websocket:
            self.jugadores["X"] = None
            self.nombres["X"] = "Esperando..."
        elif self.jugadores["O"] == websocket:
            self.jugadores["O"] = None
            self.nombres["O"] = "Esperando..."
        if len(self.conexiones) == 0:
            self.tablero = [""] * 9
            self.turno = "X"
            self.jugadores = {"X": None, "O": None}
            self.nombres = {"X": "Esperando...", "O": "Esperando..."}

    async def enviar_a_todos(self, mensaje: dict):
        for conexion in self.conexiones:
            await conexion.send_json(mensaje)

    async def procesar_movimiento(self, indice: int, jugador: str):
        if self.tablero[indice] == "" and self.turno == jugador:
            self.tablero[indice] = jugador
            ganador = self.verificar_ganador()
            if ganador:
                await self.enviar_a_todos({"tipo": "fin_juego", "tablero": self.tablero, "ganador": ganador})
                self.tablero = [""] * 9
                self.turno = "X"
            else:
                self.turno = "O" if jugador == "X" else "X"
                await self.enviar_a_todos({"tipo": "actualizacion", "tablero": self.tablero, "turno": self.turno})

manager = GameManager()

# ==========================================
# 3. RUTAS DE LA APP
# ==========================================
app = FastAPI(title="Gato Multijugador")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
html_path = os.path.join(FRONTEND_DIR, "index.html")
manifest_path = os.path.join(FRONTEND_DIR, "manifest.json")

@app.get("/")
async def get(): return FileResponse(html_path)

@app.get("/manifest.json")
async def get_manifest(): return FileResponse(manifest_path)

# --- RUTAS DE SEGURIDAD ---

@app.post("/registro")
async def registro(nombre: str, contrasena: str, db: Session = Depends(get_db)):
    # 1. Buscamos si el usuario ya existe
    perfil = db.query(Perfil).filter(Perfil.nombre == nombre).first()
    if perfil:
        return {"error": "Ese nombre ya está ocupado. Elige otro."}
    
    # 2. Si no existe, lo creamos con su contraseña licuada
    nuevo_perfil = Perfil(nombre=nombre, password_hash=encriptar_password(contrasena), victorias=0)
    db.add(nuevo_perfil)
    db.commit()
    return {"mensaje": "Cuenta creada con éxito. Ya puedes iniciar sesión."}

@app.post("/login")
async def login(nombre: str, contrasena: str, db: Session = Depends(get_db)):
    # 1. Buscamos al usuario
    perfil = db.query(Perfil).filter(Perfil.nombre == nombre).first()
    
    # 2. Comparamos los jugos de la licuadora
    if not perfil or perfil.password_hash != encriptar_password(contrasena):
        return {"error": "Usuario o contraseña incorrectos."}
        
    return {"mensaje": "Éxito", "nombre": perfil.nombre, "victorias": perfil.victorias}

# --------------------------

@app.post("/registrar_partida")
async def registrar_partida(nombre_ganador: str, nombre_perdedor: str, db: Session = Depends(get_db)):
    perfil_ganador = db.query(Perfil).filter(Perfil.nombre == nombre_ganador).first()
    perfil_perdedor = db.query(Perfil).filter(Perfil.nombre == nombre_perdedor).first()

    if perfil_ganador and perfil_perdedor:
        perfil_ganador.victorias += 1
        nueva_partida = Partida(ganador_id=perfil_ganador.id, perdedor_id=perfil_perdedor.id)
        db.add(nueva_partida)
        db.commit()
        return {"victorias": perfil_ganador.victorias}
    return {"error": "Hubo un error al guardar la partida."}

@app.websocket("/ws/{nombre_usuario}")
async def websocket_endpoint(websocket: WebSocket, nombre_usuario: str):
    await manager.conectar(websocket, nombre_usuario)
    try:
        while True:
            data = await websocket.receive_json()
            if data["accion"] == "mover":
                await manager.procesar_movimiento(data["indice"], data["jugador"])
    except WebSocketDisconnect:
        manager.desconectar(websocket)