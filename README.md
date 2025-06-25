# Noddle Trader 🍜🍜

**Estrategia de Trading Automatizada ICT MSS (Market Structure Shift) con Fair Value Gaps**

Un sistema de trading automatizado que implementa la metodología ICT (Inner Circle Trader) para detectar cambios en la estructura del mercado y operar en base a Fair Value Gaps (FVG) en el mercado Forex.

## 🎯 Características Principales

- **Estrategia ICT MSS**: Detección de cambios en la estructura del mercado
- **Fair Value Gaps (FVG)**: Identificación y mitigación de gaps de valor justo
- **Multi-timeframe**: Análisis en M15 para sesgo direccional y M1 para entradas
- **Gestión de Riesgo**: Risk/Reward configurable con stop loss dinámico
- **Análisis en Tiempo Real**: Monitoreo continuo del mercado
- **Logging Detallado**: Sistema de logs para debugging y análisis
- **Filtros de Sesión**: Opcional filtrado por sesión de Nueva York

## 📋 Requisitos Previos

### Software Necesario

1. **Python 3.13+**
2. **MetaTrader 5** (Desktop)
   - Cuenta demo o real activa
   - Terminal MT5 ejecutándose
3. **Poetry** (Gestor de dependencias)

### Instalación de Poetry

```bash
# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Linux/Mac
curl -sSL https://install.python-poetry.org | python3 -
```

## 🚀 Instalación

### 1. Clonar el Repositorio

```bash
git clone <repository-url>
cd noddle-trader
```

### 2. Instalar Dependencias

```bash
# Instalar dependencias del proyecto
poetry install

# Activar el entorno virtual
poetry shell
```

### 3. Configurar MetaTrader 5

1. **Abrir MetaTrader 5**
2. **Habilitar Algoritmic Trading**:
   - Tools → Options → Expert Advisors
   - ✅ "Allow algorithmic trading"
   - ✅ "Allow DLL imports"
3. **Configurar Símbolos**:
   - Asegurar que EURUSD esté disponible en Market Watch

## ⚙️ Configuración

### Parámetros Principales

El archivo `main.py` contiene la configuración principal:

```python
def cargar_configuracion():
    return {
        # --- Parámetros de Riesgo ---
        "CUENTA_INICIAL": 10000,           # Capital inicial
        "RIESGO_POR_OPERACION": 0.01,      # 1% de riesgo por operación
        "RR": 1.5,                         # Risk/Reward ratio
        "VALOR_POR_PIP": 10,               # USD por pip
        
        # --- Parámetros de Análisis ---
        "SYMBOL": "EURUSD",                # Símbolo a operar
        "VELAS_M15": 15,                   # Velas M15 para análisis
        "VELAS_M1": 7,                     # Velas M1 para FVG  
        "USAR_FILTRO_SESION": False,       # Filtro sesión NY
        
        # --- Ejecución ---
        "INTERVALO_ANALISIS": 5,           # Segundos entre análisis
    }
```

### Configuración Avanzada (strategy.py)

```python
# Tolerancias y filtros
"TOLERANCIA_MITIGACION": 0.00015,      # Tolerancia para FVG
"UMBRAL_SESION": 0.0002,               # Umbral para sesgo
"RANGO_MINIMO_VELA": 0.0003,           # Rango mínimo de vela válida
```

## 🎮 Uso

### Modo Tiempo Real

```bash
# Ejecutar el sistema completo
poetry run python -m noddle_trader.main

# O si ya estás en el shell de poetry
python -m noddle_trader.main
```

### Modo Desarrollo

```bash
# Ejecutar solo el data feed para pruebas
poetry run python -m noddle_trader.data_feed

# Ejecutar con logging detallado
PYTHONPATH=src poetry run python -m noddle_trader.main
```

## 📊 Funcionamiento de la Estrategia

### 1. Análisis de Sesgo (M15)
- **Break of Structure**: Ruptura de máximos/mínimos recientes
- **Tendencia**: Análisis del desplazamiento de precios
- **Sesgo Direccional**: Alcista o Bajista

### 2. Detección de FVG (M1)
- **Fair Value Gap Alcista**: Gap entre vela previa high y vela actual low
- **Fair Value Gap Bajista**: Gap entre vela previa low y vela actual high
- **Mitigación**: Precio retorna al área del gap

### 3. Gestión de Entradas
- **Entrada**: Al confirmar mitigación del FVG
- **Stop Loss**: Low/High de la vela del medio del FVG
- **Take Profit**: Basado en Risk/Reward ratio configurado

### 4. Gestión de Riesgo
- **Tamaño de Posición**: Calculado según % de riesgo
- **Risk/Reward**: Configurable (default 1:1.5)
- **Stop Loss Dinámico**: Basado en estructura del mercado

## 📁 Estructura del Proyecto

```
noddle-trader/
├── src/
│   └── noddle_trader/
│       ├── __init__.py
│       ├── main.py           # Punto de entrada principal
│       ├── strategy.py       # Lógica de la estrategia ICT
│       ├── data_feed.py      # Conexión y datos MT5
│       └── utils/
├── tests/                    # Tests unitarios
├── docs/                     # Documentación
├── pyproject.toml           # Configuración Poetry
├── README.md                # Este archivo
└── .gitignore
```

## 🔧 Componentes Técnicos

### MT5DataFeed
- **Conexión MT5**: Manejo robusto de la conexión
- **Datos Históricos**: Obtención eficiente de datos OHLC
- **Validación**: Verificación de integridad de datos
- **Timeframes**: Soporte M1, M5, M15, M30, H1, H4, D1

### ICTMSSStrategy
- **Análisis Multi-timeframe**: M15 para sesgo, M1 para entrada
- **Detección FVG**: Algoritmo optimizado para Fair Value Gaps
- **Gestión de Riesgo**: Cálculo automático de lotes y niveles
- **Logging**: Sistema completo de trazabilidad

## 📈 Métricas y Estadísticas

El sistema proporciona:
- **Total de Operaciones**
- **Win Rate** (% de operaciones ganadoras)
- **Profit Factor** (Ganancia/Pérdida)
- **Registro de Operaciones** con timestamps

## 🚨 Advertencias y Consideraciones

### ⚠️ Riesgos
- **Trading en Vivo**: Este sistema puede realizar operaciones reales
- **Pérdidas**: El trading conlleva riesgo de pérdidas financieras
- **Backtesting**: Siempre probar en cuenta demo primero

### 🔒 Seguridad
- **Cuenta Demo**: Usar cuenta demo para pruebas
- **Validación**: Validar todas las configuraciones antes de usar
- **Monitoreo**: Supervisar el sistema durante la operación

### 📋 Limitaciones
- **Dependencia MT5**: Requiere MetaTrader 5 funcionando
- **Símbolo Único**: Actualmente configurado solo para EURUSD
- **Sesión**: Optimizado para mercado Forex (24h)

## 🐛 Troubleshooting

### Problemas Comunes

**Error de Conexión MT5**
```bash
# Verificar que MT5 esté abierto y funcionando
# Verificar que algorithmic trading esté habilitado
# Revisar logs en la consola
```

**No se obtienen datos**
```bash
# Verificar símbolo en Market Watch
# Verificar conexión a internet
# Revisar configuración de timeframes
```

**Errores de dependencias**
```bash
# Reinstalar dependencias
poetry install --no-cache

# Verificar versión de Python
python --version  # Debe ser >= 3.13
```

## 🧪 Testing

```bash
# Ejecutar tests
poetry run pytest

# Tests con coverage
poetry run pytest --cov=noddle_trader

# Tests específicos
poetry run pytest tests/test_strategy.py
```

## 🤝 Contribución

1. Fork el proyecto
2. Crear branch para feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push al branch (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.

## 👤 Autor

**Angelo Ojeda**
- Email: angelomihaelle@gmail.com
- GitHub: [@angelomihaelle](https://github.com/angelomihaelle)

## 🙏 Agradecimientos

- **ICT (Inner Circle Trader)** por la metodología de trading
- **MetaQuotes** por MetaTrader 5 y su API Python
- **Comunidad de Trading** por el feedback y mejoras continuas

---

## 📞 Soporte

Para soporte técnico o preguntas:
1. **Issues**: Crear un issue en GitHub
2. **Email**: angelomihaelle@gmail.com
3. **Documentación**: Revisar logs y documentación técnica

---

**⚠️ DISCLAIMER**: Este software es para fines educativos y de investigación. El trading conlleva riesgos significativos. Nunca opere con dinero que no puede permitirse perder. Siempre pruebe en cuenta demo antes de usar fondos reales.
