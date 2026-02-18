# -*- coding: utf-8 -*-
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import SessionLocal, engine
import models
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt

# ==========================================
# 1. CONFIGURACIÓN E INICIO DEL SERVIDOR
# ==========================================

# Crea las tablas en Supabase automáticamente
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FruverOS Pro")

# --- SEGURIDAD Y JWT ---
SECRET_KEY = "fruver_2026_secreto_para_produccion" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- MIDDLEWARE (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario temporal para códigos admin
TOKENS_ADMIN = {}

# --- DEPENDENCIAS ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 2. RUTAS DE NAVEGACIÓN
# ==========================================

@app.get("/")
async def root():
    return RedirectResponse(url="/static/login.html")

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 3. MODELOS DE DATOS
# ==========================================

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    rol: str

# ==========================================
# 4. FUNCIONES DE SEGURIDAD
# ==========================================

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión expirada o inválida",
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
# 5. AUTENTICACIÓN (LOGIN Y REGISTRO)
# ==========================================

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existe = db.query(models.User).filter(models.User.username == user.username).first()
    if existe: 
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    # Normalizamos a MAYÚSCULAS para evitar errores de comparación
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
        "rol": user.rol.upper()  # Siempre devolvemos en mayúsculas
    }

# ==========================================
# 6. SEGURIDAD ADMIN (CORREGIDO)
# ==========================================

@app.get("/admin/generar-codigo")
def generar_codigo_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.rol.upper() != 'ADMIN':
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")
    
    codigo = ''.join(random.choices(string.digits, k=4))
    TOKENS_ADMIN[codigo] = datetime.now()
    return {"codigo": codigo}

@app.post("/cambiar-password-dinamico")
def cambiar_pass_dinamico(user_id: int, nueva_pass: str, token_admin: str, db: Session = Depends(get_db)):
    if token_admin not in TOKENS_ADMIN:
        raise HTTPException(status_code=400, detail="Código de administrador inválido o expirado")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user: 
        user.password = get_password_hash(nueva_pass.strip())
        db.commit()
        if token_admin in TOKENS_ADMIN: del TOKENS_ADMIN[token_admin]
    return {"status": "success"}

@app.get("/admin/usuarios")
def listar_usuarios_admin(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.rol.upper() != 'ADMIN':
        return []
    usuarios = db.query(models.User).all()
    # Cambiado a formato objeto para mejor lectura del JS
    return [{"id": u.id, "username": u.username, "rol": u.rol} for u in usuarios]

# ==========================================
# 7. OPERACIONES (COMPRA, VENTA, PAGO)
# ==========================================

@app.post("/comprar")
def registrar_compra(proveedor: str, producto: str, cantidad: float, precio_unitario: float, unidad: str, fecha_manual: str = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre == proveedor.upper(), models.Proveedor.owner_id == current_user.id).first()
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
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre == cliente.upper(), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        prov = models.Proveedor(nombre=cliente.upper(), owner_id=current_user.id)
        db.add(prov); db.commit(); db.refresh(prov)
    
    f_obj = datetime.strptime(fecha_manual, "%Y-%m-%d") if fecha_manual and fecha_manual.strip() else datetime.now()
    nuevo = models.Movimiento(tipo='VENTA', producto="DESPACHO TOTAL DÍA", monto=monto_total, fecha=f_obj, proveedor_id=prov.id)
    db.add(nuevo); db.commit()
    return {"status": "success"}

@app.post("/pagar")
def registrar_pago(proveedor: str, monto: float, detalle_pago: str = "ABONO", fecha_manual: str = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre == proveedor.upper(), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        prov = models.Proveedor(nombre=proveedor.upper(), owner_id=current_user.id)
        db.add(prov); db.commit(); db.refresh(prov)
    
    f_obj = datetime.strptime(fecha_manual, "%Y-%m-%d") if fecha_manual and fecha_manual.strip() else datetime.now()
    nuevo = models.Movimiento(tipo='PAGO', producto=detalle_pago.upper(), monto=monto, fecha=f_obj, proveedor_id=prov.id)
    db.add(nuevo); db.commit()
    return {"status": "success"}

# ==========================================
# 8. CONSULTAS E HISTORIAL
# ==========================================

@app.get("/historial")
def obtener_historial(skip: int = 0, limit: int = 50, nombre: Optional[str] = None, fecha: Optional[str] = None, tipo: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Movimiento).join(models.Proveedor)

    if nombre:
        query = query.filter(models.Proveedor.nombre.ilike(f"%{nombre}%"))
    if fecha:
        query = query.filter(func.date(models.Movimiento.fecha) == fecha)
    if tipo and tipo != "TODO":
        query = query.filter(models.Movimiento.tipo == tipo)

    total_registros = query.count()
    movimientos = query.order_by(desc(models.Movimiento.fecha)).offset(skip).limit(limit).all()

    return {"total": total_registros, "data": [{
        "id": m.id,
        "fecha": m.fecha.strftime("%Y-%m-%d %H:%M"),
        "tipo": m.tipo,
        "producto": m.producto or "N/A",
        "proveedor": m.proveedor.nombre,
        "monto": float(m.monto),
        "pagado": m.pagado,
        "cantidad": float(m.cantidad or 0),
        "precio_unitario": float(m.precio_unitario or 0)
    } for m in movimientos]}

# ==========================================
# 9. DASHBOARD Y ANÁLISIS
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

        mov_v = db.query(models.Movimiento).filter(models.Movimiento.proveedor_id == p.id, models.Movimiento.pagado == False, models.Movimiento.tipo != 'PAGO').order_by(models.Movimiento.fecha.asc()).first()
        mora = (hoy - mov_v.fecha).days if mov_v and mov_v.fecha else 0
        
        info = {"nombre": p.nombre, "saldo": f"$ {abs(saldo):,.0f}", "saldo_num": abs(saldo), "dias_mora": mora}

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

@app.get("/analisis/ventas-semanales")
def ventas_semanales(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    hoy = datetime.now(); labels = []; ventas = []; compras = []
    for i in range(-5, 1):
        dia = hoy + timedelta(days=i); dia_f = dia.date()
        label = f"{dia.day}/{dia.month}"
        
        v = float(db.query(func.sum(models.Movimiento.monto)).join(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id, models.Movimiento.tipo == 'VENTA', func.date(models.Movimiento.fecha) == dia_f).scalar() or 0)
        c = float(db.query(func.sum(models.Movimiento.monto)).join(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id, models.Movimiento.tipo == 'COMPRA', func.date(models.Movimiento.fecha) == dia_f).scalar() or 0)
        
        labels.append(label); ventas.append(v); compras.append(c)
    return {"labels": labels, "ventas": ventas, "compras": compras}

@app.get("/analisis/resumen_dias")
def resumen_dias(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(models.Movimiento).join(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id).all()
    agrupado = {}
    for m in query:
        f = m.fecha.strftime("%Y-%m-%d")
        if f not in agrupado:
            agrupado[f] = {"fecha": f, "items": 0, "total_movido": 0, "pendiente_pagar": 0, "pendiente_cobrar": 0}
        
        agrupado[f]["items"] += 1
        agrupado[f]["total_movido"] += float(m.monto)
        
        if not m.pagado:
            if m.tipo == 'COMPRA': agrupado[f]["pendiente_pagar"] += float(m.monto)
            elif m.tipo == 'VENTA': agrupado[f]["pendiente_cobrar"] += float(m.monto)
            
    return sorted(list(agrupado.values()), key=lambda x: x['fecha'], reverse=True)

# ==========================================
# 10. CIERRES Y ACCIONES DE DEPURE
# ==========================================

@app.delete("/borrar_dia_completo")
def borrar_dia_completo(fecha: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    mis_provs = db.query(models.Proveedor.id).filter(models.Proveedor.owner_id == current_user.id).subquery()
    movs = db.query(models.Movimiento).filter(models.Movimiento.proveedor_id.in_(mis_provs), func.date(models.Movimiento.fecha) == fecha).all()
    for m in movs: db.delete(m)
    db.commit()
    return {"status": "success"}

@app.post("/pagar_rango_fechas")
def pagar_rango_fechas(nombre: str, f_inicio: str, f_fin: str, monto_real: float, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prov = db.query(models.Proveedor).filter(models.Proveedor.nombre.ilike(nombre.strip()), models.Proveedor.owner_id == current_user.id).first()
    if not prov:
        raise HTTPException(status_code=404, detail="Persona no encontrada")

    nuevo_pago = models.Movimiento(tipo='PAGO', producto=f"SALDO {f_inicio} AL {f_fin}", monto=monto_real, fecha=datetime.now(), proveedor_id=prov.id, pagado=True)
    db.add(nuevo_pago)
    
    deudas = db.query(models.Movimiento).filter(
        models.Movimiento.proveedor_id == prov.id, 
        models.Movimiento.pagado == False, 
        func.date(models.Movimiento.fecha) >= f_inicio, 
        func.date(models.Movimiento.fecha) <= f_fin
    ).all()
    
    for d in deudas: 
        d.pagado = True
        d.fecha_pago = datetime.now()
        
    db.commit()
    return {"status": "success"}

@app.get("/proveedores")
def listar_proveedores_cortos(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Proveedor).filter(models.Proveedor.owner_id == current_user.id).all()

@app.delete("/movimiento/{mov_id}")
def eliminar_movimiento_unico(mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(models.Movimiento).filter(models.Movimiento.id == mov_id).first()
    if mov: 
        db.delete(mov)
        db.commit()
    return {"status": "success"}

@app.post("/marcar_pagado/{mov_id}")
def cambiar_estado_pagado(mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(models.Movimiento).filter(models.Movimiento.id == mov_id).first()
    if not mov: raise HTTPException(status_code=404)
    
    mov.pagado = not mov.pagado
    if mov.pagado: mov.fecha_pago = datetime.now()
    db.commit()
    return {"status": "success", "nuevo_estado": mov.pagado}
