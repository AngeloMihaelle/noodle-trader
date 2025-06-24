# strategy.py
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, Optional, Tuple
import logging
import toml
import os
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

class ICTMSSStrategy:
    """
    Estrategia ICT mejorada con logging detallado y almacenamiento de análisis.
    - Sesgo de Dirección (Bias) en M15 por ruptura de estructura (Break of Structure).
    - Entrada en M1 por retroceso a un Fair Value Gap (FVG).
    - Gestión de riesgo flexible y Stop Loss optimizado.
    - Optimización de velocidad: usa último sesgo válido, tolerancia al rango y filtro de ruido.
    - Almacenamiento de todos los análisis en archivos TOML para revisión posterior.
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
        
        # Configuración para almacenamiento de análisis
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        self.analysis_counter = 0
        
        logging.info(f"📁 Directorio de salida configurado: {self.output_dir}")

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

    def _determinar_sesgo_m15(self, df_m15: pd.DataFrame) -> Tuple[Optional[str], Optional[float], Dict]:
        """
        Determina el sesgo y retorna información detallada para almacenamiento
        """
        logging.info("--- 1. Analizando sesgo en M15 ---")
        
        analysis_data = {
            "timestamp": datetime.now().isoformat(),
            "velas_disponibles": len(df_m15),
            "velas_minimas_requeridas": self.MIN_VELAS_M15,
            "sesgo_determinado": None,
            "razon_sesgo": None,
            "precio_actual": None,
            "swing_high": None,
            "swing_low": None,
            "tendencia_calculada": None,
            "ultimo_sesgo_valido_usado": self.ultimo_sesgo_valido
        }
        
        if len(df_m15) < self.MIN_VELAS_M15:
            analysis_data["sesgo_determinado"] = None
            analysis_data["razon_sesgo"] = f"Velas insuficientes: {len(df_m15)} < {self.MIN_VELAS_M15}"
            logging.warning(f"No hay suficientes velas en M15 ({len(df_m15)} de {self.MIN_VELAS_M15}).")
            return None, None, analysis_data
            
        ultimas = df_m15.tail(self.MIN_VELAS_M15)
        high, low, precio = ultimas["high"].max(), ultimas["low"].min(), ultimas.iloc[-1]["close"]
        
        analysis_data.update({
            "precio_actual": float(precio),
            "swing_high": float(high),
            "swing_low": float(low)
        })
        
        logging.info(f"Swing High: {high:.5f}, Swing Low: {low:.5f}, Precio actual: {precio:.5f}")
        
        # Lógica de determinación de sesgo
        if precio > high:
            analysis_data["sesgo_determinado"] = "alcista"
            analysis_data["razon_sesgo"] = "Precio rompió swing high"
            logging.info("✅ Sesgo ALCISTA confirmado.")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high, analysis_data
            
        elif precio < low:
            analysis_data["sesgo_determinado"] = "bajista"
            analysis_data["razon_sesgo"] = "Precio rompió swing low"
            logging.info("✅ Sesgo BAJISTA confirmado.")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low, analysis_data
            
        elif precio > high - self.UMBRAL_SESION:
            analysis_data["sesgo_determinado"] = "alcista"
            analysis_data["razon_sesgo"] = f"Precio cerca de swing high (umbral: {self.UMBRAL_SESION})"
            logging.info("⚠️ Sesgo ALCISTA suave (umbral alcanzado).")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high, analysis_data
            
        elif precio < low + self.UMBRAL_SESION:
            analysis_data["sesgo_determinado"] = "bajista"
            analysis_data["razon_sesgo"] = f"Precio cerca de swing low (umbral: {self.UMBRAL_SESION})"
            logging.info("⚠️ Sesgo BAJISTA suave (umbral alcanzado).")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low, analysis_data

        # Calcular tendencia reciente
        tendencia = ultimas["close"].iloc[-1] - ultimas["close"].iloc[0]
        analysis_data["tendencia_calculada"] = float(tendencia)
        
        if tendencia > 0:
            analysis_data["sesgo_determinado"] = "alcista"
            analysis_data["razon_sesgo"] = f"Tendencia alcista por desplazamiento: {tendencia:.5f}"
            logging.info("📈 Tendencia alcista detectada por desplazamiento de precio. Aplicando sesgo ALCISTA.")
            self.ultimo_sesgo_valido = "alcista"
            return "alcista", high, analysis_data
            
        elif tendencia < 0:
            analysis_data["sesgo_determinado"] = "bajista"
            analysis_data["razon_sesgo"] = f"Tendencia bajista por desplazamiento: {tendencia:.5f}"
            logging.info("📉 Tendencia bajista detectada por desplazamiento de precio. Aplicando sesgo BAJISTA.")
            self.ultimo_sesgo_valido = "bajista"
            return "bajista", low, analysis_data
        
        # Usar último sesgo válido
        if self.ultimo_sesgo_valido:
            analysis_data["sesgo_determinado"] = self.ultimo_sesgo_valido
            analysis_data["razon_sesgo"] = "Usando último sesgo válido"
            logging.info("Sesgo indefinido. Aplicando último sesgo válido.")
            return self.ultimo_sesgo_valido, None, analysis_data
        
        analysis_data["sesgo_determinado"] = None
        analysis_data["razon_sesgo"] = "No se pudo determinar sesgo"
        logging.info("No se pudo determinar sesgo.")
        return None, None, analysis_data

    def _vela_valida(self, vela: pd.Series) -> bool:
        rango = vela["high"] - vela["low"]
        es_valida = rango >= self.RANGO_MINIMO_VELA
        logging.debug(f"Vela validación -> Rango: {rango:.5f} - {'✅' if es_valida else '❌'}")
        return es_valida

    def _buscar_fvg_y_entrada_m1(self, df_m1: pd.DataFrame, sesgo: str) -> Tuple[Optional[Dict], Dict]:
        """
        Busca FVG y retorna señal de entrada junto con datos de análisis
        """
        logging.info("--- 2. Buscando FVG en M1 ---")
        
        analysis_data = {
            "velas_m1_disponibles": len(df_m1),
            "sesgo_aplicado": sesgo,
            "fvg_detectados": [],
            "fvg_memoria_count": len(self.fvg_memoria),
            "entrada_generada": False,
            "razon_entrada": None,
            "tolerancia_mitigacion": self.TOLERANCIA_MITIGACION
        }
        
        if len(df_m1) < 5:
            analysis_data["razon_entrada"] = "Velas insuficientes en M1"
            logging.warning("No hay suficientes velas en M1 para analizar FVG.")
            return None, analysis_data

        reciente = df_m1.iloc[-1]
        fvg_detectados = []

        # Buscar nuevos FVGs
        for i in range(len(df_m1) - 5, 2, -1):
            v_previa, v_fvg, v_actual = df_m1.iloc[i - 2], df_m1.iloc[i - 1], df_m1.iloc[i]
            if not all(map(self._vela_valida, [v_previa, v_fvg, v_actual])):
                continue

            fvg_info = None
            if sesgo == "alcista" and v_actual['low'] > v_previa['high']:
                logging.info(f"FVG ALCISTA detectado en índice {i}.")
                fvg_info = {
                    "direccion": "compra",
                    "fvg_alto": float(v_actual['low']),
                    "fvg_bajo": float(v_previa['high']),
                    "stop_loss": float(v_fvg['low']),
                    "indice": i,
                    "timestamp": str(df_m1.index[i])
                }
                fvg_detectados.append(fvg_info)
                
            elif sesgo == "bajista" and v_actual['high'] < v_previa['low']:
                logging.info(f"FVG BAJISTA detectado en índice {i}.")
                fvg_info = {
                    "direccion": "venta",
                    "fvg_alto": float(v_previa['low']),
                    "fvg_bajo": float(v_actual['high']),
                    "stop_loss": float(v_fvg['high']),
                    "indice": i,
                    "timestamp": str(df_m1.index[i])
                }
                fvg_detectados.append(fvg_info)

        analysis_data["fvg_detectados"] = fvg_detectados
        self.fvg_memoria = fvg_detectados[:3] + self.fvg_memoria[:5]  # limitar memoria

        # Verificar mitigación
        precio_reciente = {
            "high": float(reciente['high']),
            "low": float(reciente['low']),
            "close": float(reciente['close']),
            "timestamp": str(reciente.name)
        }
        analysis_data["precio_reciente"] = precio_reciente

        for idx, fvg in enumerate(self.fvg_memoria):
            mitigacion_info = {
                "fvg_index": idx,
                "fvg_direccion": fvg['direccion'],
                "mitigado": False,
                "tipo_mitigacion": None,
                "distancia_para_mitigacion": None
            }
            
            if fvg['direccion'] == 'compra':
                distancia = abs(reciente['low'] - fvg['fvg_alto'])
                mitigacion_info["distancia_para_mitigacion"] = float(distancia)
                
                if reciente['low'] <= fvg['fvg_alto'] and reciente['close'] > fvg['fvg_bajo']:
                    mitigacion_info.update({
                        "mitigado": True,
                        "tipo_mitigacion": "mitigacion_completa"
                    })
                    analysis_data["entrada_generada"] = True
                    analysis_data["razon_entrada"] = f"FVG mitigado completamente (índice {idx})"
                    logging.info("✅ FVG mitigado. Entrada COMPRA.")
                    
                    return {
                        "direccion": "compra",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }, analysis_data
                    
                elif distancia <= self.TOLERANCIA_MITIGACION:
                    mitigacion_info.update({
                        "mitigado": True,
                        "tipo_mitigacion": "mitigacion_por_proximidad"
                    })
                    analysis_data["entrada_generada"] = True
                    analysis_data["razon_entrada"] = f"Entrada anticipada por proximidad (distancia: {distancia:.5f})"
                    logging.info("⚠️ Entrada anticipada COMPRA por proximidad al FVG.")
                    
                    return {
                        "direccion": "compra",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }, analysis_data
                    
            elif fvg['direccion'] == 'venta':
                distancia = abs(reciente['high'] - fvg['fvg_bajo'])
                mitigacion_info["distancia_para_mitigacion"] = float(distancia)
                
                if reciente['high'] >= fvg['fvg_bajo'] and reciente['close'] < fvg['fvg_alto']:
                    mitigacion_info.update({
                        "mitigado": True,
                        "tipo_mitigacion": "mitigacion_completa"
                    })
                    analysis_data["entrada_generada"] = True
                    analysis_data["razon_entrada"] = f"FVG mitigado completamente (índice {idx})"
                    logging.info("✅ FVG mitigado. Entrada VENTA.")
                    
                    return {
                        "direccion": "venta",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }, analysis_data
                    
                elif distancia <= self.TOLERANCIA_MITIGACION:
                    mitigacion_info.update({
                        "mitigado": True,
                        "tipo_mitigacion": "mitigacion_por_proximidad"
                    })
                    analysis_data["entrada_generada"] = True
                    analysis_data["razon_entrada"] = f"Entrada anticipada por proximidad (distancia: {distancia:.5f})"
                    logging.info("⚠️ Entrada anticipada VENTA por proximidad al FVG.")
                    
                    return {
                        "direccion": "venta",
                        "precio_entrada": reciente['close'],
                        "stop_loss": fvg['stop_loss'],
                        "timestamp": reciente.name
                    }, analysis_data
            
            analysis_data.setdefault("mitigaciones_evaluadas", []).append(mitigacion_info)

        analysis_data["razon_entrada"] = "No se encontró FVG válido mitigado"
        logging.info("No se encontró FVG válido mitigado ni cercano.")
        return None, analysis_data

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

    def _guardar_analisis_toml(self, analysis_data: Dict):
        """
        Guarda el análisis completo en un archivo TOML
        """
        self.analysis_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{self.analysis_counter:04d}_{timestamp}.toml"
        filepath = self.output_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                toml.dump(analysis_data, f)
            logging.info(f"📊 Análisis guardado en: {filepath}")
        except Exception as e:
            logging.error(f"Error al guardar análisis: {e}")

    def analizar_mercado(self, df_m15: pd.DataFrame, df_m1: pd.DataFrame) -> Optional[Dict]:
        logging.info("================== INICIANDO NUEVO ANÁLISIS DE MERCADO ==================")
        
        # Preparar estructura de datos completa para el análisis
        analysis_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "analysis_id": self.analysis_counter + 1,
                "version": "1.0"
            },
            "configuracion": {
                "cuenta_inicial": self.CUENTA_INICIAL,
                "riesgo_por_operacion": self.RIESGO_POR_OPERACION,
                "rr_ratio": self.RR,
                "min_velas_m15": self.MIN_VELAS_M15,
                "min_velas_m1": self.MIN_VELAS_M1,
                "usar_filtro_sesion": self.USAR_FILTRO_SESION,
                "tolerancia_mitigacion": self.TOLERANCIA_MITIGACION,
                "umbral_sesion": self.UMBRAL_SESION,
                "rango_minimo_vela": self.RANGO_MINIMO_VELA
            },
            "datos_entrada": {
                "velas_m15_originales": len(df_m15),
                "velas_m1_originales": len(df_m1)
            }
        }
        
        # Filtrar datos
        df_m15_filtrado = self._filtrar_sesion_ny(df_m15)
        df_m1_filtrado = self._filtrar_sesion_ny(df_m1)
        
        analysis_data["datos_filtrados"] = {
            "velas_m15_filtradas": len(df_m15_filtrado),
            "velas_m1_filtradas": len(df_m1_filtrado),
            "filtro_aplicado": self.USAR_FILTRO_SESION
        }
        
        if df_m15_filtrado.empty or df_m1_filtrado.empty:
            analysis_data["resultado"] = {
                "señal_generada": False,
                "razon": "Datos insuficientes tras el filtro"
            }
            self._guardar_analisis_toml(analysis_data)
            logging.info("Datos insuficientes tras el filtro.")
            return None
        
        # Determinar sesgo
        sesgo, nivel_referencia, sesgo_analysis = self._determinar_sesgo_m15(df_m15_filtrado)
        analysis_data["analisis_sesgo"] = sesgo_analysis
        
        if not sesgo:
            analysis_data["resultado"] = {
                "señal_generada": False,
                "razon": "Sesgo no determinado"
            }
            self._guardar_analisis_toml(analysis_data)
            logging.info("Sesgo no determinado. Análisis detenido.")
            return None
        
        # Buscar FVG y entrada
        señal, fvg_analysis = self._buscar_fvg_y_entrada_m1(df_m1_filtrado, sesgo)
        analysis_data["analisis_fvg"] = fvg_analysis
        
        if señal:
            # Calcular niveles
            señal_completa = self._calcular_niveles_y_lote(señal)
            if señal_completa:
                analysis_data["resultado"] = {
                    "señal_generada": True,
                    "señal": {
                        "direccion": señal_completa["direccion"],
                        "precio_entrada": float(señal_completa["precio_entrada"]),
                        "stop_loss": float(señal_completa["stop_loss"]),
                        "take_profit": float(señal_completa["take_profit"]),
                        "tamaño_lote": float(señal_completa["tamaño_lote"]),
                        "distancia_sl": float(señal_completa["distancia_sl"]),
                        "rr_ratio": señal_completa["rr_ratio"],
                        "timestamp": str(señal_completa["timestamp"])
                    }
                }
                self._guardar_analisis_toml(analysis_data)
                return señal_completa
        
        analysis_data["resultado"] = {
            "señal_generada": False,
            "razon": "No se generó señal de entrada válida"
        }
        self._guardar_analisis_toml(analysis_data)
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

    def generar_reporte_analisis(self) -> Dict:
        """
        Genera un reporte consolidado de todos los análisis almacenados
        """
        if not os.path.exists(self.output_dir):
            return {"error": "Directorio de análisis no encontrado"}
        
        archivos_toml = list(self.output_dir.glob("analysis_*.toml"))
        if not archivos_toml:
            return {"error": "No se encontraron archivos de análisis"}
        
        reporte = {
            "total_analisis": len(archivos_toml),
            "señales_generadas": 0,
            "señales_rechazadas": 0,
            "razones_rechazo": {},
            "sesgos_detectados": {"alcista": 0, "bajista": 0, "indefinido": 0},
            "tipos_entrada": {},
            "estadisticas_fvg": {"total_detectados": 0, "promedio_por_analisis": 0}
        }
        
        total_fvg = 0
        for archivo in archivos_toml:
            try:
                with open(archivo, 'r', encoding='utf-8') as f:
                    data = toml.load(f)
                
                # Analizar resultado
                if data.get("resultado", {}).get("señal_generada", False):
                    reporte["señales_generadas"] += 1
                else:
                    reporte["señales_rechazadas"] += 1
                    razon = data.get("resultado", {}).get("razon", "Sin razón")
                    reporte["razones_rechazo"][razon] = reporte["razones_rechazo"].get(razon, 0) + 1
                
                # Analizar sesgo
                sesgo = data.get("analisis_sesgo", {}).get("sesgo_determinado")
                if sesgo in ["alcista", "bajista"]:
                    reporte["sesgos_detectados"][sesgo] += 1
                else:
                    reporte["sesgos_detectados"]["indefinido"] += 1
                
                # Analizar FVG
                fvg_detectados = len(data.get("analisis_fvg", {}).get("fvg_detectados", []))
                total_fvg += fvg_detectados
                
                # Analizar tipo de entrada
                razon_entrada = data.get("analisis_fvg", {}).get("razon_entrada")
                if razon_entrada and "mitigado" in razon_entrada:
                    tipo = "mitigacion_completa" if "completamente" in razon_entrada else "mitigacion_proximidad"
                    reporte["tipos_entrada"][tipo] = reporte["tipos_entrada"].get(tipo, 0) + 1
                    
            except Exception as e:
                logging.error(f"Error procesando {archivo}: {e}")
        
        reporte["estadisticas_fvg"]["total_detectados"] = total_fvg
        reporte["estadisticas_fvg"]["promedio_por_analisis"] = total_fvg / len(archivos_toml) if archivos_toml else 0
        
        # Guardar reporte
        reporte_path = self.output_dir / "reporte_consolidado.toml"
        reporte["generado_en"] = datetime.now().isoformat()
        
        try:
            with open(reporte_path, 'w', encoding='utf-8') as f:
                toml.dump(reporte, f)
            logging.info(f"📈 Reporte consolidado guardado en: {reporte_path}")
        except Exception as e:
            logging.error(f"Error al guardar reporte consolidado: {e}")
        
        return reporte