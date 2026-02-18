from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_
from database import SessionLocal, engine
import models
from datetime import datetime, timedelta
from typing import Optional, List
from passlib.context import CryptContext
from jose import JWTError, jwt
import random
import string
from pydantic import BaseModel

# ==========================================
# 1. CONFIGURACION INICIAL DEL SERVIDOR
# ==========================================

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="FruverOS Pro")

# --- CONFIGURACION DE SEGURIDAD ---
SECRET_KEY = "cambia_esto_por_una_clave_larga_y_aleatoria_en_produccion"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    rol: str = "VENDEDOR"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

TOKENS_ADMIN = {}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# ==========================================
# 2. LOGIN Y REGISTRO
# ==========================================

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existe = db.query(models.User).filter(models.User.username == user.username).first()
    if existe: 
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    rol = "ADMIN" if user.username.lower() == "admin" else "VENDEDOR"
    hashed_pass = get_password_hash(user.password)
    
    new_user = models.User(username=user.username, password=hashed_pass, rol=rol)
    db.add(new_user)
    db.commit()
    return {"message": "Usuario creado exitosamente"}

@app.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "rol": user.rol
    }

# ==========================================
# 3. SEGURIDAD ADMIN
# ==========================================

@app.get("/admin/generar-codigo")
def generar_codigo_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.rol != 'ADMIN': raise HTTPException(status_code=403, detail="Requiere Admin")
    codigo = ''.join(random.choices(string.digits, k=4))
    TOKENS_ADMIN[codigo] = datetime.now()
    return {"codigo": codigo}

@app.post("/cambiar-password-dinamico")
def cambiar_pass_dinamico(user_id: int, nueva_pass: str, token_admin: str, db: Session = Depends(get_db)):
    if token_admin not in TOKENS_ADMIN: raise HTTPException(status_code=400, detail="Código inválido")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user: 
        user.password = get_password_hash(nueva_pass.strip())
        db.commit()
        if token_admin in TOKENS_ADMIN: del TOKENS_ADMIN[token_admin]
    return {"status": "success"}

@app.get("/admin/usuarios")
def listar_usuarios_admin(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.rol != 'ADMIN': return []
    usuarios = db.query(models.User).all()
    return [[u.id, u.username, u.rol] for u in usuarios]

# ==========================================
# 4. OPERACIONES PRINCIPALES
# ==========================================

@app.post("/comprar")
def registrar_compra(proveedor: str, producto: str, cantidad: float, precio_unitario: float, unidad: str, fecha_manual: str = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre.ilike(proveedor), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        prov = models.Proveedor(nombre=proveedor.upper(), owner_id=current_user.id)
        db.add(prov); db.commit(); db.refresh(prov)
    
    f_obj = datetime.strptime(fecha_manual, "%Y-%m-%d") if fecha_manual and fecha_manual.strip() else datetime.now()
    
    nuevo = models.Movimiento(
        tipo='COMPRA', 
        producto=f"{producto} ({unidad})", 
        cantidad=cantidad, 
        precio_unitario=precio_unitario, 
        monto=cantidad*precio_unitario, 
        fecha=f_obj, 
        proveedor_id=prov.id
    )
    db.add(nuevo); db.commit()
    return {"status": "success"}

@app.post("/despachar_total")
def registrar_despacho_total(cliente: str, monto_total: float, fecha_manual: str = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre.ilike(cliente), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        prov = models.Proveedor(nombre=cliente.upper(), owner_id=current_user.id)
        db.add(prov); db.commit(); db.refresh(prov)
    
    f_obj = datetime.strptime(fecha_manual, "%Y-%m-%d") if fecha_manual and fecha_manual.strip() else datetime.now()
    nuevo = models.Movimiento(tipo='VENTA', producto="DESPACHO TOTAL DÍA", monto=monto_total, fecha=f_obj, proveedor_id=prov.id)
    db.add(nuevo); db.commit()
    return {"status": "success"}

@app.post("/pagar")
def registrar_pago(proveedor: str, monto: float, detalle_pago: str = "ABONO / PAGO", fecha_manual: str = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre.ilike(proveedor), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        prov = models.Proveedor(nombre=proveedor.upper(), owner_id=current_user.id)
        db.add(prov); db.commit(); db.refresh(prov)
    
    f_obj = datetime.strptime(fecha_manual, "%Y-%m-%d") if fecha_manual and fecha_manual.strip() else datetime.now()
    nuevo = models.Movimiento(tipo='PAGO', producto=detalle_pago.upper(), monto=monto, fecha=f_obj, proveedor_id=prov.id)
    db.add(nuevo); db.commit()
    return {"status": "success"}

# ==========================================
# 5. HISTORIAL (CORREGIDO Y OPTIMIZADO)
# ==========================================

# ==========================================
# 5. HISTORIAL (CORREGIDO)
# ==========================================

@app.get("/historial")
def obtener_historial(
    skip: int = 0, 
    limit: int = 10, 
    nombre: Optional[str] = None, 
    fecha: Optional[str] = None, 
    tipo: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # 1. Iniciamos la consulta uniendo Movimientos con Proveedor
    query = db.query(models.Movimiento).join(models.Proveedor)

    # 2. Aplicamos filtros solo si el usuario envió datos
    if nombre:
        query = query.filter(models.Proveedor.nombre.ilike(f"%{nombre}%"))
    
    if fecha:
        query = query.filter(func.date(models.Movimiento.fecha) == fecha)

    if tipo and tipo != "TODO":
        query = query.filter(models.Movimiento.tipo == tipo)

    # 3. Contamos el total ANTES de cortar la lista
    total_registros = query.count()

    # 4. Obtenemos los datos ordenados por fecha
    movimientos = query.order_by(desc(models.Movimiento.fecha)).offset(skip).limit(limit).all()

    # 5. Serializamos los datos
    data_response = []
    for m in movimientos:
        data_response.append({
            "id": m.id,
            "fecha": m.fecha.strftime("%Y-%m-%d %H:%M"),
            "tipo": m.tipo,
            "producto": m.producto or "N/A",
            "proveedor": m.proveedor.nombre,
            "monto": float(m.monto),
            "pagado": m.pagado,
            # --- AGREGADO: Datos que faltaban ---
            "cantidad": float(m.cantidad) if m.cantidad else 0,
            "precio_unitario": float(m.precio_unitario) if m.precio_unitario else 0
        })

    return {"total": total_registros, "data": data_response}
# ==========================================
# 6. DASHBOARD
# ==========================================

@app.get("/saldos-generales")
def saldos_generales(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    mis_proveedores = db.query(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id).all()
    res_deudas = []; res_cobros = []; t_yo = 0; t_baratta = 0
    hoy = datetime.now()

    for p in mis_proveedores:
        c = float(db.query(func.sum(models.Movimiento.monto)).filter(models.Movimiento.proveedor_id == p.id, models.Movimiento.tipo == 'COMPRA', models.Movimiento.pagado == False).scalar() or 0)
        v = float(db.query(func.sum(models.Movimiento.monto)).filter(models.Movimiento.proveedor_id == p.id, models.Movimiento.tipo == 'VENTA', models.Movimiento.pagado == False).scalar() or 0)
        pa = float(db.query(func.sum(models.Movimiento.monto)).filter(models.Movimiento.proveedor_id == p.id, models.Movimiento.tipo == 'PAGO', models.Movimiento.pagado == False).scalar() or 0)
        
        saldo = (v if v > 0 else c) - pa

        dias_mora = 0
        mov_viejo = db.query(models.Movimiento).filter(
            models.Movimiento.proveedor_id == p.id,
            models.Movimiento.pagado == False,
            models.Movimiento.tipo != 'PAGO'
        ).order_by(models.Movimiento.fecha.asc()).first()

        if mov_viejo and mov_viejo.fecha:
            dias_mora = (hoy - mov_viejo.fecha).days

        info = {
            "nombre": p.nombre, 
            "saldo": f"$ {abs(saldo):,.0f}", 
            "saldo_num": abs(saldo), 
            "dias_mora": dias_mora
        }

        if v > 0:
            t_baratta += saldo
            if saldo != 0: res_cobros.append(info)
        else:
            t_yo += saldo
            if saldo != 0: res_deudas.append(info)

    return {
        "proveedores": res_deudas, 
        "clientes": res_cobros, 
        "total_yo_debo_num": t_yo,            
        "total_baratta_debe_num": t_baratta, 
        "balance_num": t_baratta - t_yo      
    }

# ==========================================
# 7. ANALISIS (INDENTACIÓN CORREGIDA)
# ==========================================

@app.get("/analisis/ventas-semanales")
def ventas_semanales(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    mis_proveedores = db.query(models.Proveedor.id).filter(models.Proveedor.owner_id == current_user.id).subquery()
    hoy = datetime.now()
    labels = []; ventas = []; compras = []

    for i in range(-5, 6): 
        dia = hoy + timedelta(days=i)
        dia_f = dia.date()
        ms = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        ds = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        label = f"{dia.day} {ms[dia.month-1]} ({ds[dia.weekday()]})"
        
        v = float(db.query(func.sum(models.Movimiento.monto)).filter(models.Movimiento.proveedor_id.in_(mis_proveedores), models.Movimiento.tipo == 'VENTA', func.date(models.Movimiento.fecha) == dia_f).scalar() or 0)
        c = float(db.query(func.sum(models.Movimiento.monto)).filter(models.Movimiento.proveedor_id.in_(mis_proveedores), models.Movimiento.tipo == 'COMPRA', func.date(models.Movimiento.fecha) == dia_f).scalar() or 0)
        
        labels.append(label)
        ventas.append(v)
        compras.append(c)

    return {"labels": labels, "ventas": ventas, "compras": compras}

# ==========================================
# 8. CIERRES Y PAGOS (LOGICA SEGURA)
# ==========================================

@app.get("/analisis/resumen_dias")
def resumen_dias(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Traemos todos los movimientos
    query = db.query(models.Movimiento).join(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id).all()
    agrupado = {}
    
    for m in query:
        f = m.fecha.strftime("%Y-%m-%d") if m.fecha else "---"
        
        # Si el día no existe en el diccionario, lo inicializamos con contadores en 0
        if f not in agrupado:
            agrupado[f] = {
                "fecha": f, 
                "items": 0, 
                "total_movido": 0,
                "pendiente_pagar": 0,   # Deuda (Compras sin pagar)
                "pendiente_cobrar": 0   # Cobro (Ventas sin cobrar)
            }
        
        item = agrupado[f]
        item["items"] += 1
        item["total_movido"] += float(m.monto)

        # --- LÓGICA DE BLOQUEO ---
        # Si el movimiento NO está pagado, sumamos a la deuda pendiente de ese día
        if not m.pagado:
            if m.tipo == 'COMPRA':
                item["pendiente_pagar"] += float(m.monto)
            elif m.tipo == 'VENTA':
                item["pendiente_cobrar"] += float(m.monto)

    resultado = list(agrupado.values())
    resultado.sort(key=lambda x: x['fecha'], reverse=True)
    return resultado

@app.delete("/borrar_dia_completo")
def borrar_dia_completo(fecha: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    mis_provs = db.query(models.Proveedor.id).filter(models.Proveedor.owner_id == current_user.id).subquery()
    movs = db.query(models.Movimiento).filter(models.Movimiento.proveedor_id.in_(mis_provs), func.date(models.Movimiento.fecha) == fecha).all()
    for m in movs: db.delete(m)
    db.commit()
    return {"status": "success"}

@app.post("/pagar_rango_fechas")
def pagar_rango_fechas(
    nombre: str, 
    f_inicio: str, 
    f_fin: str, 
    monto_real: float, 
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # 1. Buscar al proveedor
    prov = db.query(models.Proveedor).filter(
        models.Proveedor.nombre.ilike(nombre.strip()), 
        models.Proveedor.owner_id == current_user.id
    ).first()
    
    if not prov:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    # 2. Registrar el PAGO en el sistema
    nuevo_pago = models.Movimiento(
        tipo='PAGO', 
        producto=f"ABONO FACTURAS {f_inicio} AL {f_fin}", 
        monto=monto_real, 
        fecha=datetime.now(), 
        proveedor_id=prov.id, 
        pagado=True
    )
    db.add(nuevo_pago)
    
    # 3. Buscar deudas pendientes
    deudas = db.query(models.Movimiento).filter(
        models.Movimiento.proveedor_id == prov.id, 
        models.Movimiento.tipo.in_(['COMPRA', 'VENTA']), 
        models.Movimiento.pagado == False, 
        func.date(models.Movimiento.fecha) >= f_inicio, 
        func.date(models.Movimiento.fecha) <= f_fin
    ).order_by(models.Movimiento.fecha.asc()).all() 

    # 4. ALGORITMO DE CONCILIACIÓN (Seguro)
    dinero_disponible = monto_real

    for deuda in deudas:
        if dinero_disponible <= 0:
            break 
            
        monto_deuda = float(deuda.monto)

        if dinero_disponible >= monto_deuda:
            deuda.pagado = True
            deuda.fecha_pago = datetime.now()
            dinero_disponible -= monto_deuda
        else:
            dinero_disponible = 0 

    db.commit()
    return {"status": "success", "mensaje": "Pago distribuido correctamente"}

@app.get("/proveedores")
def listar_proveedores(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id).all()

@app.delete("/movimiento/{mov_id}")
def eliminar_movimiento(mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(models.Movimiento).filter(models.Movimiento.id == mov_id).first()
    if mov: db.delete(mov); db.commit()
    return {"status": "success"}

    # --- PEGAR ESTO AL FINAL DE main.py ---

@app.post("/marcar_pagado/{mov_id}")
def marcar_movimiento_pagado(mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(models.Movimiento).filter(models.Movimiento.id == mov_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    
    # Invertimos el estado (si estaba pagado pasa a no pagado y viceversa)
    mov.pagado = not mov.pagado
    
    # Si se marca como pagado, actualizamos la fecha
    if mov.pagado:
        mov.fecha_pago = datetime.now()
        
    db.commit()

    return {"status": "success", "nuevo_estado": mov.pagado}
