from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# --- MODELO DE USUARIOS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    rol = Column(String, default="VENDEDOR") 
    
    proveedores = relationship("Proveedor", back_populates="owner")

# --- MODELO DE PROVEEDORES/CLIENTES ---
class Proveedor(Base):
    __tablename__ = "proveedores"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="proveedores")
    movimientos = relationship("Movimiento", back_populates="proveedor", cascade="all, delete-orphan")

# --- MODELO DE MOVIMIENTOS (Actualizado para Nivel Pro) ---
class Movimiento(Base):
    __tablename__ = "movimientos"
    id = Column(Integer, primary_key=True, index=True)
    
    tipo = Column(String) # COMPRA, VENTA, PAGO
    producto = Column(String, nullable=True) 

    # 1. CAMBIO DE FLOAT A NUMERIC: 
    # Garantiza que no se pierdan centavos en las cuentas (Precisión de 10 dígitos, 2 decimales)
    cantidad = Column(Numeric(10, 2), default=0)
    precio_unitario = Column(Numeric(10, 2), default=0)
    monto = Column(Numeric(10, 2), default=0)
    
    # 2. CAMBIO DE STRING A DATETIME:
    # Esto permite que la base de datos ordene las deudas y moras por tiempo real, no por texto.
    fecha = Column(DateTime, default=datetime.now) 
    created_at = Column(DateTime, default=datetime.now) 
    
    # Relaciones
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"))
    proveedor = relationship("Proveedor", back_populates="movimientos")

    # Campos de Conciliación (Se mantienen intactos)
    pagado = Column(Boolean, default=False)  
    fecha_pago = Column(DateTime, nullable=True)