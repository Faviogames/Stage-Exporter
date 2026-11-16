# WRC to ACR Stage Exporter

**Stage Exporter 1.5** es un complemento para Windows que amplía Sando Rally Stage Export Tool 0.3.7. Permite exportar tramos de WRC Generations a Assetto Corsa Rally, seleccionar qué tramos instala el pack y reutilizar los que ya están construidos.

## Requisitos

- Sando Rally Stage Export Tool **0.3.7**, instalado por separado.
- WRC Generations y Assetto Corsa Rally instalados localmente.
- Assetto Corsa Rally cerrado durante la instalación del pack.

## Instalar

Descarga el ZIP desde [GitHub Releases](https://github.com/Faviogames/Stage-Exporter/releases/latest) y descomprímelo.

Coloca esta carpeta junto a la instalación de Sando y ejecuta `INSTALAR.bat`. Si el instalador no detecta la ruta automáticamente, selecciona la carpeta que contiene `_internal\wrcg2acr-worker.exe`. El instalador genera **WRC to ACR Stage Exporter.exe** en la carpeta de Sando. Abre ese ejecutable tras finalizar la instalación.

En la ventana **Stage Exporter**, elige un tramo y pulsa **Exportar tramo**. Usa **Actualizar pack** para instalar los tramos marcados. El pack se guarda en `acr/Content/Paks/~mods` y las exportaciones aparecen en el juego bajo `[MOD] <país>`.

Este repositorio contiene el código y la configuración del complemento. El núcleo de Sando y los recursos de los juegos se usan desde las instalaciones locales. La compatibilidad de los tramos depende del inventario de esta versión.

Consulta [README_INSTALLER.txt](README_INSTALLER.txt) para más detalles.
