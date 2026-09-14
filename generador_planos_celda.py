# -*- coding: utf-8 -*-
"""
generador_planos_celda.py

Script estandarizado para generar el plano (layout 2D, vista de planta)
de una celda de robot. Lo armé para no tener que dibujar cada celda desde
cero en CAD: aquí solo describo los elementos de la celda en una lista
(robot, cerca de seguridad, mesas, banda, controlador, puertas, etc.) y
el script arma el plano completo con cajetín, cotas de referencia y
escala, listo para exportar a PNG y PDF.

Uso:
    1. Modificar el diccionario ELEMENTOS_CELDA y los datos del CAJETIN
       más abajo (sección "EJEMPLO DE USO / DATOS DE LA CELDA").
    2. Correr el script.
    3. Los planos quedan guardados en la carpeta /salida como .png y .pdf.

Autor: Annette Michell Valenzuela Rodríguez
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrow
import os
from datetime import datetime

# =============================================================================
# 1. CONFIGURACIÓN GENERAL DEL PLANO
# =============================================================================
# Dejo esto como constantes al inicio para no tener que buscar "números
# mágicos" dentro del código cada vez que quiera ajustar el estilo del plano.

ESCALA_UNIDAD = "m"          # unidad en la que voy a dar todas las medidas
TAMANO_HOJA = (16, 10)       # tamaño de la hoja en pulgadas (aprox A3 apaisado)
DPI_EXPORTACION = 300        # resolución de exportación (buena para imprimir)
CARPETA_SALIDA = "salida"

COLOR_ROBOT = "#2E86AB"
COLOR_ALCANCE_ROBOT = "#2E86AB"
COLOR_CERCA_SEGURIDAD = "#C0392B"
COLOR_MESA = "#7F8C8D"
COLOR_BANDA = "#8E7CC3"
COLOR_CONTROLADOR = "#34495E"
COLOR_PUERTA = "#27AE60"
COLOR_TEXTO = "#1B1B1B"
COLOR_EJES = "#BDBDBD"


# =============================================================================
# 2. FUNCIONES PARA DIBUJAR CADA TIPO DE ELEMENTO ESTÁNDAR
# =============================================================================
# La idea de tener una función por tipo de elemento es que el plano de
# cualquier celda nueva se arme siempre con el mismo "lenguaje visual":
# mismo color y mismo símbolo para robot, cerca, mesa, etc. Así no dependo
# de acordarme del estilo cada vez, solo agrego el elemento a la lista.

def dibujar_robot(ax, elemento):
    """
    Dibuja la base del robot y, opcionalmente, su radio de alcance máximo
    (útil para checar interferencias con mesas, bandas o la cerca).
    """
    x, y = elemento["posicion"]
    radio_base = elemento.get("radio_base", 0.3)
    radio_alcance = elemento.get("radio_alcance")

    # Base del robot
    base = patches.Circle((x, y), radio_base, facecolor=COLOR_ROBOT,
                           edgecolor="black", linewidth=1.2, zorder=5)
    ax.add_patch(base)

    # Círculo de alcance máximo (línea punteada, sin relleno)
    if radio_alcance:
        alcance = patches.Circle((x, y), radio_alcance, facecolor="none",
                                  edgecolor=COLOR_ALCANCE_ROBOT,
                                  linestyle="--", linewidth=1, alpha=0.6,
                                  zorder=1)
        ax.add_patch(alcance)

    etiqueta = elemento.get("etiqueta", "ROBOT")
    ax.text(x, y - radio_base - 0.25, etiqueta, ha="center", va="top",
            fontsize=8, color=COLOR_TEXTO, zorder=6)


def dibujar_cerca_seguridad(ax, elemento):
    """
    Dibuja el perímetro de seguridad de la celda como un rectángulo
    punteado. 'esquina' es la esquina inferior izquierda (x, y).
    """
    x, y = elemento["esquina"]
    ancho, alto = elemento["ancho"], elemento["alto"]

    cerca = patches.Rectangle((x, y), ancho, alto, facecolor="none",
                               edgecolor=COLOR_CERCA_SEGURIDAD,
                               linewidth=2, linestyle=(0, (6, 3)), zorder=2)
    ax.add_patch(cerca)

    etiqueta = elemento.get("etiqueta", "LÍMITE DE CELDA / CERCA DE SEGURIDAD")
    ax.text(x + ancho / 2, y + alto + 0.15, etiqueta, ha="center",
            va="bottom", fontsize=8, color=COLOR_CERCA_SEGURIDAD, zorder=6)


def dibujar_mesa(ax, elemento):
    """Dibuja una mesa de trabajo, fixture o superficie fija como rectángulo."""
    x, y = elemento["esquina"]
    ancho, alto = elemento["ancho"], elemento["alto"]

    mesa = patches.Rectangle((x, y), ancho, alto, facecolor=COLOR_MESA,
                              edgecolor="black", alpha=0.5, linewidth=1,
                              zorder=3)
    ax.add_patch(mesa)

    etiqueta = elemento.get("etiqueta", "MESA")
    ax.text(x + ancho / 2, y + alto / 2, etiqueta, ha="center", va="center",
            fontsize=7, color=COLOR_TEXTO, zorder=6)


def dibujar_banda(ax, elemento):
    """
    Dibuja una banda/transportador como rectángulo alargado con una
    flecha que indica el sentido del flujo de material.
    """
    x, y = elemento["esquina"]
    ancho, alto = elemento["ancho"], elemento["alto"]

    banda = patches.Rectangle((x, y), ancho, alto, facecolor=COLOR_BANDA,
                               edgecolor="black", alpha=0.5, linewidth=1,
                               zorder=3)
    ax.add_patch(banda)

    # Flecha de sentido de flujo, solo si el elemento la especifica
    if elemento.get("sentido") == "horizontal":
        flecha = FancyArrow(x + 0.1, y + alto / 2, ancho - 0.2, 0,
                             width=0.02, head_width=0.15, head_length=0.15,
                             color="black", zorder=4)
        ax.add_patch(flecha)
    elif elemento.get("sentido") == "vertical":
        flecha = FancyArrow(x + ancho / 2, y + 0.1, 0, alto - 0.2,
                             width=0.02, head_width=0.15, head_length=0.15,
                             color="black", zorder=4)
        ax.add_patch(flecha)

    etiqueta = elemento.get("etiqueta", "BANDA TRANSPORTADORA")
    ax.text(x + ancho / 2, y - 0.15, etiqueta, ha="center", va="top",
            fontsize=7, color=COLOR_TEXTO, zorder=6)


def dibujar_controlador(ax, elemento):
    """Dibuja el gabinete/controlador del robot como cuadro sólido pequeño."""
    x, y = elemento["esquina"]
    ancho, alto = elemento["ancho"], elemento["alto"]

    gabinete = patches.Rectangle((x, y), ancho, alto,
                                  facecolor=COLOR_CONTROLADOR,
                                  edgecolor="black", linewidth=1, zorder=3)
    ax.add_patch(gabinete)

    etiqueta = elemento.get("etiqueta", "CONTROLADOR")
    ax.text(x + ancho / 2, y + alto + 0.1, etiqueta, ha="center",
            va="bottom", fontsize=7, color=COLOR_TEXTO, zorder=6)


def dibujar_puerta(ax, elemento):
    """Dibuja una puerta de acceso a la celda sobre la línea de la cerca."""
    x, y = elemento["posicion"]
    ancho = elemento.get("ancho", 0.9)
    orientacion = elemento.get("orientacion", "horizontal")

    if orientacion == "horizontal":
        ax.plot([x, x + ancho], [y, y], color=COLOR_PUERTA, linewidth=4,
                 solid_capstyle="butt", zorder=6)
    else:
        ax.plot([x, x], [y, y + ancho], color=COLOR_PUERTA, linewidth=4,
                 solid_capstyle="butt", zorder=6)

    etiqueta = elemento.get("etiqueta", "ACCESO")
    ax.text(x, y - 0.2, etiqueta, ha="left", va="top", fontsize=7,
            color=COLOR_PUERTA, zorder=6)


# Diccionario que relaciona cada "tipo" de elemento con su función de
# dibujo. Si en el futuro agrego un elemento nuevo (ej. escáner de
# seguridad), solo tengo que escribir su función de dibujo y registrarla
# aquí, sin tocar el resto del script.
FUNCIONES_DIBUJO = {
    "robot": dibujar_robot,
    "cerca_seguridad": dibujar_cerca_seguridad,
    "mesa": dibujar_mesa,
    "banda": dibujar_banda,
    "controlador": dibujar_controlador,
    "puerta": dibujar_puerta,
}


# =============================================================================
# 3. CAJETÍN (TITLE BLOCK) ESTÁNDAR
# =============================================================================

def dibujar_cajetin(fig, datos_cajetin):
    """
    Dibuja el cajetín estándar en la esquina inferior derecha de la hoja,
    con los datos básicos que debería llevar cualquier plano de celda:
    nombre de la celda, número de plano, escala, quién lo elaboró,
    fecha y revisión.
    """
    ancho_cajetin, alto_cajetin = 0.32, 0.14
    x0, y0 = 1 - ancho_cajetin - 0.02, 0.02

    ax_cajetin = fig.add_axes([x0, y0, ancho_cajetin, alto_cajetin])
    ax_cajetin.set_xticks([])
    ax_cajetin.set_yticks([])
    for spine in ax_cajetin.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(1.2)

    filas = [
        f"CELDA: {datos_cajetin.get('celda', '')}",
        f"NO. DE PLANO: {datos_cajetin.get('no_plano', '')}   "
        f"REV: {datos_cajetin.get('revision', '0')}",
        f"ELABORÓ: {datos_cajetin.get('elaboro', '')}",
        f"FECHA: {datos_cajetin.get('fecha', datetime.now().strftime('%d/%m/%Y'))}"
        f"   ESCALA: {datos_cajetin.get('escala', 'S/E')}",
    ]
    for i, texto in enumerate(filas):
        ax_cajetin.text(0.03, 0.85 - i * 0.24, texto, fontsize=8,
                         color=COLOR_TEXTO, va="top", transform=ax_cajetin.transAxes)


# =============================================================================
# 4. FUNCIÓN PRINCIPAL: ARMA EL PLANO A PARTIR DE LA LISTA DE ELEMENTOS
# =============================================================================

def generar_plano(elementos, datos_cajetin, limites_plano,
                   nombre_archivo="plano_celda"):
    """
    Arma el plano completo de la celda.

    Parámetros
    ----------
    elementos : list[dict]
        Lista de elementos de la celda. Cada elemento debe traer al menos
        la llave "tipo" (uno de los definidos en FUNCIONES_DIBUJO).
    datos_cajetin : dict
        Datos para el cajetín (celda, no_plano, elaboro, fecha, escala, revision).
    limites_plano : tuple
        (x_min, x_max, y_min, y_max) en las mismas unidades del layout,
        para fijar el encuadre del plano.
    nombre_archivo : str
        Nombre base (sin extensión) con el que se guardan el PNG y el PDF.
    """
    fig, ax = plt.subplots(figsize=TAMANO_HOJA)

    # Dibujo cada elemento usando su función correspondiente. Si me
    # equivoco de "tipo" en algún elemento, prefiero que truene aquí con
    # un mensaje claro a que se dibuje mal el plano sin darme cuenta.
    for elemento in elementos:
        tipo = elemento.get("tipo")
        if tipo not in FUNCIONES_DIBUJO:
            raise ValueError(
                f"Tipo de elemento '{tipo}' no reconocido. "
                f"Tipos válidos: {list(FUNCIONES_DIBUJO.keys())}"
            )
        FUNCIONES_DIBUJO[tipo](ax, elemento)

    # Rejilla de referencia (ayuda a leer distancias a simple vista)
    x_min, x_max, y_min, y_max = limites_plano
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal")
    ax.grid(True, color=COLOR_EJES, linewidth=0.5, linestyle=":")
    ax.set_xlabel(f"X ({ESCALA_UNIDAD})")
    ax.set_ylabel(f"Y ({ESCALA_UNIDAD})")
    ax.set_title(datos_cajetin.get("celda", "PLANO DE CELDA"), fontsize=12,
                 fontweight="bold")

    dibujar_cajetin(fig, datos_cajetin)

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_png = os.path.join(CARPETA_SALIDA, f"{nombre_archivo}.png")
    ruta_pdf = os.path.join(CARPETA_SALIDA, f"{nombre_archivo}.pdf")
    fig.savefig(ruta_png, dpi=DPI_EXPORTACION, bbox_inches="tight")
    fig.savefig(ruta_pdf, bbox_inches="tight")
    plt.close(fig)

    print(f"Plano generado: {ruta_png}")
    print(f"Plano generado: {ruta_pdf}")


# =============================================================================
# 5. EJEMPLO DE USO / DATOS DE LA CELDA
# =============================================================================
# Esta sección es la única que necesito editar cuando cambio de celda:
# solo describo los elementos y los datos del cajetín, y llamo a
# generar_plano(). Dejo un ejemplo con datos genéricos como plantilla.

if __name__ == "__main__":

    ELEMENTOS_CELDA = [
        {
            "tipo": "cerca_seguridad",
            "esquina": (0, 0),
            "ancho": 6,
            "alto": 5,
        },
        {
            "tipo": "robot",
            "posicion": (3, 2.5),
            "radio_base": 0.3,
            "radio_alcance": 2.0,
            "etiqueta": "ROBOT 1",
        },
        {
            "tipo": "mesa",
            "esquina": (0.4, 0.4),
            "ancho": 1.2,
            "alto": 1.0,
            "etiqueta": "MESA DE CARGA",
        },
        {
            "tipo": "mesa",
            "esquina": (4.4, 3.6),
            "ancho": 1.2,
            "alto": 1.0,
            "etiqueta": "MESA DE DESCARGA",
        },
        {
            "tipo": "banda",
            "esquina": (1.8, 0.3),
            "ancho": 2.4,
            "alto": 0.5,
            "sentido": "horizontal",
            "etiqueta": "BANDA TRANSPORTADORA 1",
        },
        {
            "tipo": "controlador",
            "esquina": (5.3, 0.3),
            "ancho": 0.5,
            "alto": 0.7,
            "etiqueta": "CONTROLADOR ROBOT 1",
        },
        {
            "tipo": "puerta",
            "posicion": (2.5, 0),
            "ancho": 0.9,
            "orientacion": "horizontal",
            "etiqueta": "ACCESO OPERADOR",
        },
    ]

    DATOS_CAJETIN = {
        "celda": "NOMBRE_DE_LA_CELDA",
        "no_plano": "PL-XXX-001",
        "revision": "0",
        "elaboro": "Annette Michell Valenzuela Rodríguez",
        "fecha": datetime.now().strftime("%d/%m/%Y"),
        "escala": "1:50",
    }

    LIMITES_PLANO = (-0.5, 6.5, -0.5, 5.5)

    generar_plano(ELEMENTOS_CELDA, DATOS_CAJETIN, LIMITES_PLANO,
                  nombre_archivo="plano_celda_ejemplo")
