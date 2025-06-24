# data_feed.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict, List
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5DataFeed:
    """
    Clase para manejar la conexión y obtención de datos de MetaTrader 5
    Optimizada para la estrategia ICT MSS
    """

    def __init__(self):
        """Inicializar la conexión con MetaTrader 5"""
        self.connected = False
        self.timezone_utc = pytz.timezone("UTC")
        self.timezone_ny = pytz.timezone("America/New_York")

        # Mapeo de timeframes
        self.timeframes = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

        self.connect()

    def connect(self) -> bool:
        """
        Conectar a MetaTrader 5

        Returns:
            True si la conexión es exitosa, False en caso contrario
        """
        if not mt5.initialize():
            logger.error("Error al inicializar MetaTrader 5")
            logger.error(f"Error code: {mt5.last_error()}")
            return False

        self.connected = True

        # Obtener información de la cuenta
        account_info = mt5.account_info()
        if account_info is not None:
            logger.info(f"Conectado a MT5 - Cuenta: {account_info.login}")
            logger.info(f"Servidor: {account_info.server}")
            logger.info(f"Balance: {account_info.balance}")

        return True

    def disconnect(self):
        """Desconectar de MetaTrader 5"""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("Desconectado de MetaTrader 5")

    def is_connected(self) -> bool:
        """Verificar si está conectado a MT5"""
        return self.connected and mt5.terminal_info() is not None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Obtener información del símbolo

        Args:
            symbol: Símbolo a consultar

        Returns:
            Diccionario con información del símbolo o None
        """
        if not self.is_connected():
            logger.error("No hay conexión con MT5")
            return None

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Símbolo {symbol} no encontrado")
            return None

        return {
            "name": symbol_info.name,
            "digits": symbol_info.digits,
            "point": symbol_info.point,
            "spread": symbol_info.spread,
            "trade_mode": symbol_info.trade_mode,
            "min_lot": symbol_info.volume_min,
            "max_lot": symbol_info.volume_max,
            "lot_step": symbol_info.volume_step,
        }

    def obtener_datos_historicos(
        self, symbol: str, timeframe: str, desde: datetime, hasta: datetime
    ) -> pd.DataFrame:
        """
        Obtener datos históricos con manejo de errores mejorado

        Args:
            symbol: Símbolo a consultar
            timeframe: Marco temporal ('M1', 'M15', etc.)
            desde: Fecha de inicio
            hasta: Fecha de fin

        Returns:
            DataFrame con datos históricos
        """
        if not self.is_connected():
            logger.error("No hay conexión con MT5")
            return pd.DataFrame()

        if timeframe not in self.timeframes:
            logger.error(f"Timeframe {timeframe} no válido")
            return pd.DataFrame()

        try:
            # Convertir fechas a UTC si no están en UTC
            if desde.tzinfo is None:
                desde = self.timezone_utc.localize(desde)
            else:
                desde = desde.astimezone(self.timezone_utc)

            if hasta.tzinfo is None:
                hasta = self.timezone_utc.localize(hasta)
            else:
                hasta = hasta.astimezone(self.timezone_utc)

            # Obtener datos
            mt5_timeframe = self.timeframes[timeframe]
            rates = mt5.copy_rates_range(symbol, mt5_timeframe, desde, hasta)

            if rates is None or len(rates) == 0:
                logger.warning(f"No se obtuvieron datos para {symbol} {timeframe}")
                logger.warning(f"Error MT5: {mt5.last_error()}")
                return pd.DataFrame()

            # Crear DataFrame
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.set_index("time", inplace=True)

            # Añadir columnas útiles
            df["hl2"] = (df["high"] + df["low"]) / 2  # Precio medio
            df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3  # Precio típico
            df["ohlc4"] = (
                df["open"] + df["high"] + df["low"] + df["close"]
            ) / 4  # Precio promedio

            logger.info(f"Obtenidos {len(df)} registros de {symbol} {timeframe}")
            return df

        except Exception as e:
            logger.error(f"Error al obtener datos históricos: {e}")
            return pd.DataFrame()

    def obtener_datos_por_velas(
        self, symbol: str, timeframe: str, num_velas: int
    ) -> pd.DataFrame:
        """
        Obtener un número específico de velas desde ahora hacia atrás

        Args:
            symbol: Símbolo a consultar
            timeframe: Marco temporal
            num_velas: Número de velas a obtener

        Returns:
            DataFrame con datos históricos
        """
        if not self.is_connected():
            logger.error("No hay conexión con MT5")
            return pd.DataFrame()

        if timeframe not in self.timeframes:
            logger.error(f"Timeframe {timeframe} no válido")
            return pd.DataFrame()

        try:
            mt5_timeframe = self.timeframes[timeframe]
            rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, num_velas)

            if rates is None or len(rates) == 0:
                logger.warning(f"No se obtuvieron datos para {symbol} {timeframe}")
                return pd.DataFrame()

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.set_index("time", inplace=True)

            # Añadir columnas calculadas
            df["hl2"] = (df["high"] + df["low"]) / 2
            df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
            df["ohlc4"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4

            return df

        except Exception as e:
            logger.error(f"Error al obtener datos por velas: {e}")
            return pd.DataFrame()

    def obtener_tick_actual(self, symbol: str) -> Optional[Dict]:
        """
        Obtener el tick actual del símbolo

        Args:
            symbol: Símbolo a consultar

        Returns:
            Diccionario con información del tick actual
        """
        if not self.is_connected():
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return {
            "time": datetime.fromtimestamp(tick.time, tz=pytz.UTC),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "spread": tick.ask - tick.bid,
        }

    def filtrar_sesion_trading(
        self, df: pd.DataFrame, sesion: str = "NY"
    ) -> pd.DataFrame:
        """
        Filtrar datos por sesión de trading

        Args:
            df: DataFrame con datos
            sesion: Sesión a filtrar ('NY', 'LONDON', 'ASIA')

        Returns:
            DataFrame filtrado
        """
        if df.empty:
            return df

        df_copy = df.copy()

        # Convertir índice a timezone NY para filtrado
        if sesion == "NY":
            df_ny = df_copy.tz_convert("America/New_York")
            # Sesión de NY: 9:30 AM - 4:00 PM EST
            mask = (df_ny.index.time >= datetime.strptime("09:30", "%H:%M").time()) & (
                df_ny.index.time <= datetime.strptime("16:00", "%H:%M").time()
            )
            return df_copy[mask]

        elif sesion == "LONDON":
            df_london = df_copy.tz_convert("Europe/London")
            # Sesión de Londres: 8:00 AM - 4:30 PM GMT
            mask = (
                df_london.index.time >= datetime.strptime("08:00", "%H:%M").time()
            ) & (df_london.index.time <= datetime.strptime("16:30", "%H:%M").time())
            return df_copy[mask]

        elif sesion == "ASIA":
            df_tokyo = df_copy.tz_convert("Asia/Tokyo")
            # Sesión de Asia: 9:00 AM - 6:00 PM JST
            mask = (
                df_tokyo.index.time >= datetime.strptime("09:00", "%H:%M").time()
            ) & (df_tokyo.index.time <= datetime.strptime("18:00", "%H:%M").time())
            return df_copy[mask]

        return df_copy

    def validar_datos(self, df: pd.DataFrame) -> bool:
        """
        Validar integridad de los datos

        Args:
            df: DataFrame a validar

        Returns:
            True si los datos son válidos
        """
        if df.empty:
            return False

        # Verificar columnas necesarias
        required_columns = ["open", "high", "low", "close", "tick_volume"]
        if not all(col in df.columns for col in required_columns):
            logger.error("Faltan columnas necesarias en los datos")
            return False

        # Verificar valores faltantes
        if df[required_columns].isnull().any().any():
            logger.warning("Encontrados valores faltantes en los datos")

        # Verificar lógica de precios OHLC
        invalid_ohlc = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        )

        if invalid_ohlc.any():
            logger.warning(
                f"Encontradas {invalid_ohlc.sum()} velas con lógica OHLC inválida"
            )

        return True

    def obtener_datos_para_estrategia(
        self, symbol: str, velas_m15: int = 50, velas_m1: int = 200
    ) -> tuple:
        """
        Obtener datos optimizados para la estrategia ICT MSS

        Args:
            symbol: Símbolo a analizar
            velas_m15: Número de velas M15 a obtener
            velas_m1: Número de velas M1 a obtener

        Returns:
            Tuple con (df_m15, df_m1)
        """
        logger.info(f"Obteniendo datos para estrategia: {symbol}")

        # Obtener datos M15
        df_m15 = self.obtener_datos_por_velas(symbol, "M15", velas_m15)

        # Obtener datos M1
        df_m1 = self.obtener_datos_por_velas(symbol, "M1", velas_m1)

        # Validar datos
        if not self.validar_datos(df_m15):
            logger.error("Datos M15 inválidos")
            return pd.DataFrame(), pd.DataFrame()

        if not self.validar_datos(df_m1):
            logger.error("Datos M1 inválidos")
            return pd.DataFrame(), pd.DataFrame()

        # Filtrar por sesión NY
        df_m15_ny = self.filtrar_sesion_trading(df_m15, "NY")
        df_m1_ny = self.filtrar_sesion_trading(df_m1, "NY")

        logger.info(
            f"Datos M15: {len(df_m15)} velas total, {len(df_m15_ny)} en sesión NY"
        )
        logger.info(f"Datos M1: {len(df_m1)} velas total, {len(df_m1_ny)} en sesión NY")

        return df_m15, df_m1


# Instancia global del data feed
data_feed = MT5DataFeed()


# Funciones de compatibilidad con el código existente
def obtener_datos_r(
    symbol: str, timeframe, desde: datetime, hasta: datetime
) -> pd.DataFrame:
    """
    Función de compatibilidad con el código existente

    Args:
        symbol: Símbolo
        timeframe: Timeframe de MT5
        desde: Fecha inicio
        hasta: Fecha fin

    Returns:
        DataFrame con datos
    """
    # Mapear timeframe de MT5 a string
    timeframe_map = {
        mt5.TIMEFRAME_M1: "M1",
        mt5.TIMEFRAME_M5: "M5",
        mt5.TIMEFRAME_M15: "M15",
        mt5.TIMEFRAME_M30: "M30",
        mt5.TIMEFRAME_H1: "H1",
        mt5.TIMEFRAME_H4: "H4",
        mt5.TIMEFRAME_D1: "D1",
    }

    tf_str = timeframe_map.get(timeframe, "M15")
    return data_feed.obtener_datos_historicos(symbol, tf_str, desde, hasta)


def obtener_datos():
    """Función de compatibilidad para obtener datos de ejemplo"""
    symbol = "EURUSD"

    print("🔄 Obteniendo datos con sistema mejorado...")

    # Obtener datos para estrategia
    df_m15, df_m1 = data_feed.obtener_datos_para_estrategia(symbol)

    if not df_m15.empty:
        print("📊 Datos M15:")
        print(df_m15.tail())

        # Información adicional
        print(f"\n📈 Estadísticas M15:")
        print(f"Rango: {df_m15.index.min()} a {df_m15.index.max()}")
        print(f"Último precio: {df_m15.iloc[-1]['close']:.5f}")

    if not df_m1.empty:
        print("\n📊 Datos M1:")
        print(df_m1.tail())

        print(f"\n📈 Estadísticas M1:")
        print(f"Rango: {df_m1.index.min()} a {df_m1.index.max()}")
        print(f"Último precio: {df_m1.iloc[-1]['close']:.5f}")

    # Información del símbolo
    symbol_info = data_feed.get_symbol_info(symbol)
    if symbol_info:
        print(f"\n💰 Info del símbolo {symbol}:")
        print(f"Dígitos: {symbol_info['digits']}")
        print(f"Spread: {symbol_info['spread']} puntos")
        print(f"Lote mín: {symbol_info['min_lot']}")

    # Tick actual
    tick = data_feed.obtener_tick_actual(symbol)
    if tick:
        print(f"\n⚡ Tick actual:")
        print(f"Bid: {tick['bid']:.5f}")
        print(f"Ask: {tick['ask']:.5f}")
        print(f"Spread: {tick['spread']*10000:.1f} pips")


if __name__ == "__main__":
    try:
        obtener_datos()
    finally:
        data_feed.disconnect()
