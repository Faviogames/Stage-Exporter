# WRC to ACR Stage Exporter

**Stage Exporter 1.6.2** es un complemento para Windows que amplía Sando Rally Stage Export Tool 0.3.7. Permite exportar tramos de WRC Generations a Assetto Corsa Rally, seleccionar qué tramos instala el pack y reutilizar los que ya están construidos.

## Requisitos

- Sando Rally Stage Export Tool **0.3.7**, instalado por separado.
- WRC Generations y Assetto Corsa Rally instalados localmente.
- Assetto Corsa Rally cerrado durante la instalación del pack.

## Instalar

Descarga [Stage-Exporter-v1.6.2-Instalar.zip](https://github.com/Faviogames/Stage-Exporter/releases/download/v1.6.2/Stage-Exporter-v1.6.2-Instalar.zip). Extrae su contenido directamente dentro de la carpeta de Sando: deben quedar `payload/`, `INSTALAR.bat` y las guías en ese nivel, sin otra carpeta contenedora.

Ejecuta `INSTALAR.bat` en la carpeta de Sando. Si el instalador no detecta la ruta automáticamente, selecciona la carpeta que contiene `_internal\wrcg2acr-worker.exe`. El instalador genera **WRC to ACR Stage Exporter.exe** en la carpeta de Sando. Abre ese ejecutable tras finalizar la instalación.

En la ventana **Stage Exporter**, elige un tramo y pulsa **Exportar tramo**. Usa **Actualizar pack** para instalar los tramos marcados. El pack se guarda en `acr/Content/Paks/~mods` y las exportaciones aparecen en el juego bajo `[MOD] <país>`.

Este repositorio contiene el código y la configuración del complemento. El núcleo de Sando y los recursos de los juegos se usan desde las instalaciones locales. La compatibilidad de los tramos depende del inventario de esta versión.

Consulta [README_INSTALLER.txt](README_INSTALLER.txt) para más detalles.

## Actualizaciones

Desde la versión 1.6, la aplicación comprueba la última release de GitHub en cada inicio. Si hay una versión estable más reciente, pregunta si deseas instalarla y reiniciar. La descarga se verifica mediante SHA-256 de GitHub; si no hay conexión, puedes seguir usando el programa. Se conservan las configuraciones existentes, imágenes, descripciones, cachés y tramos; se incorporan los archivos de configuración que falten.

Los usuarios de 1.5 o anteriores, y quienes tengan ACR 26756580, deben instalar 1.6.2 manualmente (ZIP `-Instalar`). Los cambios visuales en mapas requieren reconstruir el tramo; actualizar la aplicación o el pack no reconstruye las cachés antiguas.

La versión 1.6.2 acepta ZIPs directos y el formato anterior. El archivo sin el sufijo `-Instalar` es un paquete de compatibilidad para el actualizador 1.6; para instalación manual usa el enlace anterior.
