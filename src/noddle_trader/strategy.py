# strategy.py
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, Optional, Tuple
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

class ICTMSSStrategy:
    """
    Estrategia ICT mejorada con logging detallado.
    - Sesgo de Dirección (Bias) en M15 por ruptura de estructura (Break of Structure).
    - Entrada en M1 por retroceso a un Fair Value Gap (FVG).
    - Gestión de riesgo flexible y Stop Loss optimizado.
    - Optimización de velocidad: usa último sesgo válido, tolerancia al rango y filtro de ruido.
    """

    def __init__(self, config: Dict):
        self.TOLERANCIA_MITIGACION = config.get("TOLERANCIA_MITIGACION", 0.00015)
        self.fvg_memoria = []
        logging.info("🚀 Inicializando la estrategia ICTMSSStrategy...")
        self.CUENTA_INICIAL = config.get("CUENTA_INICIAL", 10000)
        self.RIESGO_POR_OPERACION = config.get("RIESGO_POR_OPERACION", 0.01)
        self.RR = config.get("RR", 2)
        self.VALOR_POR_PIP = config.get("VALOR_POR_PIP", 10)

        self.MIN_VELAS_M15 = config.get("VELAS_M15", 20)
        self.MIN_VELAS_M1 = config.get("VELAS_M1", 50)
        self.USAR_FILTRO_SESION = config.get("USAR_FILTRO_SESION", False)
        self.UMBRAL_SESION = config.get("UMBRAL_SESION", 0.0002)
        self.RANGO_MINIMO_VELA = config.get("RANGO_MINIMO_VELA", 0.0003)

        self.operaciones = []
        self.ultimo_sesgo_valido = None

    def _filtrar_sesion_ny(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.USAR_FILTRO_SESION:
            logging.debug("Filtro de sesión desactivado. Usando todos los datos.")
            return df
        df_copy = df.copy()
        if df_copy.index.tz is None:
            df_copy.index = df_copy.index.tz_localize('UTC')
        df_ny = df_copy.tz_convert("America/New_York")
        mask = (df_ny.index.time >= time(0, 0)) & (df_ny.index.time <= time(23, 59))
        df_filtrado = df_copy[mask]
        logging.info(f"Filtradas {len(df_filtrado)} de {len(df_copy)} velas según sesión.")
        return df_filtrado

    def _determinar_sesgo_m15(self, df_m15: pd.DataFrame) -> Tuple[Optional[str], Optional[float]]:
        logging.info("--- 1. Analizando sesgo en M15 ---")
        if len(df_m15) < self.MIN_VELAS_M15:
            logging.warning(f"No hay suficientes velas en M15 ({len(df_m15)} de {self.MIN_VELAS_M15}).")
            return None, None
        ultimas = df_m15.tail(self.MIN_VELAS_M15)
        high, low, precio = ultimas["high"].max(), ultimas["low"].min(), ultimas.iloc[-1]["close"]
        logging.info(f"Swing High: {high:.5f}, Swing Low: {low:.5f}, Precio actual: {precio:.5f}")
        if precio > high:
            logging.info("✅ Sesgo ALCISTA confirmado.")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high
        elif precio < low:
            logging.info("✅ Sesgo BAJISTA confirmado.")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low
        elif precio > high - self.UMBRAL_SESION:
            logging.info("⚠️ Sesgo ALCISTA suave (umbral alcanzado).")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high
        elif precio < low + self.UMBRAL_SESION:
            logging.info("⚠️ Sesgo BAJISTA suave (umbral alcanzado).")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low

        # Nueva lógica: calcular tendencia reciente
        tendencia = ultimas["close"].iloc[-1] - ultimas["close"].iloc[0]
        if tendencia > 0:
            logging.info("📈 Tendencia alcista detectada por desplazamiento de precio. Aplicando sesgo ALCISTA.")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high
        elif tendencia < 0:
            logging.info("📉 Tendencia bajista detectada por desplazamiento de precio. Aplicando sesgo BAJISTA.")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low

        logging.info("Sesgo indefinido. Aplicando último sesgo válido si existe.")
        return (self.ultimo_sesgo_valido, None) if self.ultimo_sesgo_valido else (None, None)

    def _vela_valida(self, vela: pd.Series) -> bool:
        rango = vela["high"] - vela["low"]
        es_valida = rango >= self.RANGO_MINIMO_VELA
        logging.debug(f"Vela validación -> Rango: {rango:.5f} - {'✅' if es_valida else '❌'}")
        return es_valida

    def _buscar_fvg_y_entrada_m1(self, df_m1: pd.DataFrame, sesgo: str) -> Optional[Dict]:
        logging.info("--- 2. Buscando FVG en M1 ---")
        if len(df_m1) < 5:
            logging.warning("No hay suficientes velas en M1 para analizar FVG.")
            return None

        reciente = df_m1.iloc[-1]
        fvg_detectados = []

        for i in range(len(df_m1) - 5, 2, -1):
            v_previa, v_fvg, v_actual = df_m1.iloc[i - 2], df_m1.iloc[i - 1], df_m1.iloc[i]
            if not all(map(self._vela_valida, [v_previa, v_fvg, v_actual])):
                continue

            if sesgo == "alcista" and v_actual['low'] > v_previa['high']:
                logging.info(f"FVG ALCISTA detectado en índice {i}.")
                fvg_detectados.append({
                    "direccion": "compra",
                    "fvg_alto": v_actual['low'],
                    "fvg_bajo": v_previa['high'],
                    "stop_loss": v_fvg['low']
                })
            elif sesgo == "bajista" and v_actual['high'] < v_previa['low']:
                logging.info(f"FVG BAJISTA detectado en índice {i}.")
                fvg_detectados.append({
                    "direccion": "venta",
                    "fvg_alto": v_previa['low'],
                    "fvg_bajo": v_actual['high'],
                    "stop_loss": v_fvg['high']
                })

        self.fvg_memoria = fvg_detectados[:3] + self.fvg_memoria[:5]  # limitar memoria

        for fvg in self.fvg_memoria:
            if fvg['direccion'] == 'compra':
                if reciente['low'] <= fvg['fvg_alto'] and reciente['close'] > fvg['fvg_bajo']:
                    logging.info("✅ FVG mitigado. Entrada COMPRA.")
                    return {
                        "direccion": "compra",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }
                elif abs(reciente['low'] - fvg['fvg_alto']) <= self.TOLERANCIA_MITIGACION:
                    logging.info("⚠️ Entrada anticipada COMPRA por proximidad al FVG.")
                    return {
                        "direccion": "compra",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }
            elif fvg['direccion'] == 'venta':
                if reciente['high'] >= fvg['fvg_bajo'] and reciente['close'] < fvg['fvg_alto']:
                    logging.info("✅ FVG mitigado. Entrada VENTA.")
                    return {
                        "direccion": "venta",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }
                elif abs(reciente['high'] - fvg['fvg_bajo']) <= self.TOLERANCIA_MITIGACION:
                    logging.info("⚠️ Entrada anticipada VENTA por proximidad al FVG.")
                    return {
                        "direccion": "venta",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }

        logging.info("No se encontró FVG válido mitigado ni cercano.")
        return None
        for i in range(len(df_m1) - 3, 2, -1):
            v_previa, v_fvg, v_actual = df_m1.iloc[i - 2], df_m1.iloc[i - 1], df_m1.iloc[i]
            if not all(map(self._vela_valida, [v_previa, v_fvg, v_actual])):
                continue
            reciente = df_m1.iloc[-1]
            if sesgo == "alcista" and v_actual['low'] > v_previa['high']:
                logging.info(f"FVG ALCISTA detectado en índice {i}.")
                if reciente['low'] <= v_actual['low'] and reciente['close'] > v_previa['high']:
                    logging.info("✅ Mitigación confirmada. Generando señal de COMPRA.")
                    return {"direccion": "compra", "precio_entrada": reciente['close'], "stop_loss": v_fvg['low'], "timestamp": reciente.name}
            elif sesgo == "bajista" and v_actual['high'] < v_previa['low']:
                logging.info(f"FVG BAJISTA detectado en índice {i}.")
                if reciente['high'] >= v_actual['high'] and reciente['close'] < v_previa['low']:
                    logging.info("✅ Mitigación confirmada. Generando señal de VENTA.")
                    return {"direccion": "venta", "precio_entrada": reciente['close'], "stop_loss": v_fvg['high'], "timestamp": reciente.name}
        logging.info("No se encontró FVG válido mitigado.")
        return None

    def _calcular_niveles_y_lote(self, señal: Dict) -> Dict:
        logging.info("--- 3. Calculando niveles y tamaño de lote ---")
        sl = abs(señal["precio_entrada"] - señal["stop_loss"])
        if sl == 0:
            logging.error("SL = 0. Cancelando cálculo.")
            return None
        tp = señal["precio_entrada"] + self.RR * sl if señal["direccion"] == "compra" else señal["precio_entrada"] - self.RR * sl
        sl_pips = sl * 10000
        lote = max(0.01, round((self.CUENTA_INICIAL * self.RIESGO_POR_OPERACION) / (sl_pips * self.VALOR_POR_PIP), 2))
        señal.update({"take_profit": tp, "distancia_sl": sl, "rr_ratio": self.RR, "tamaño_lote": lote})
        logging.info(f"TP: {tp:.5f}, SL: {señal['stop_loss']:.5f}, Lote: {lote}")
        return señal

    def analizar_mercado(self, df_m15: pd.DataFrame, df_m1: pd.DataFrame) -> Optional[Dict]:
        logging.info("================== INICIANDO NUEVO ANÁLISIS DE MERCADO ==================")
        df_m15 = self._filtrar_sesion_ny(df_m15)
        df_m1 = self._filtrar_sesion_ny(df_m1)
        if df_m15.empty or df_m1.empty:
            logging.info("Datos insuficientes tras el filtro.")
            return None
        sesgo, _ = self._determinar_sesgo_m15(df_m15)
        if not sesgo:
            logging.info("Sesgo no determinado. Análisis detenido.")
            return None
        señal = self._buscar_fvg_y_entrada_m1(df_m1, sesgo)
        if señal:
            return self._calcular_niveles_y_lote(señal)
        logging.info("No se generó señal de entrada válida.")
        return None

    def simular_operacion(self, señal: Dict, df_futuro: pd.DataFrame) -> Dict:
        for _, row in df_futuro.iterrows():
            if señal["direccion"] == "compra":
                if row["low"] <= señal["stop_loss"]:
                    return {"resultado": "perdida", "precio_salida": señal["stop_loss"], "pips": (señal["stop_loss"] - señal["precio_entrada"]) * 10000}
                elif row["high"] >= señal["take_profit"]:
                    return {"resultado": "ganancia", "precio_salida": señal["take_profit"], "pips": (señal["take_profit"] - señal["precio_entrada"]) * 10000}
            else:
                if row["high"] >= señal["stop_loss"]:
                    return {"resultado": "perdida", "precio_salida": señal["stop_loss"], "pips": (señal["precio_entrada"] - señal["stop_loss"]) * 10000}
                elif row["low"] <= señal["take_profit"]:
                    return {"resultado": "ganancia", "precio_salida": señal["take_profit"], "pips": (señal["precio_entrada"] - señal["take_profit"]) * 10000}
        return {"resultado": "pendiente", "precio_salida": None, "pips": 0}

    def registrar_operacion(self, operacion: Dict):
        logging.info(f"Registrando operación: {operacion}")
        self.operaciones.append({"timestamp": datetime.now(), "operacion": operacion.copy()})

    def obtener_estadisticas(self) -> Dict:
        if not self.operaciones:
            logging.info("Sin operaciones registradas.")
            return {"total_operaciones": 0}
        total = len(self.operaciones)
        ganadas = sum(1 for op in self.operaciones if op["operacion"].get("resultado") == "ganancia")
        perdidas = total - ganadas
        win_rate = (ganadas / total) * 100
        ganancia = sum(op['operacion']['distancia_sl'] * self.RR for op in self.operaciones if op['operacion']['resultado'] == 'ganancia')
        perdida = sum(op['operacion']['distancia_sl'] for op in self.operaciones if op['operacion']['resultado'] == 'perdida')
        pf = ganancia / perdida if perdida > 0 else float('inf')
        logging.info(f"Estadísticas → Total: {total}, Win Rate: {win_rate:.2f}%, Profit Factor: {pf:.2f}")
        return {"total_operaciones": total, "ganadas": ganadas, "perdidas": perdidas, "win_rate": win_rate, "profit_factor": pf}
