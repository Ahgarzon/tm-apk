# tourmaps-android-downloads
Descargas publicas de la APK de pruebas de TourMaps, sin credenciales ni codigo privado.

## Constructor central

El workflow `TourMaps central Android pilot` utiliza un runner Linux estándar
gratuito. Consulta exclusivamente la fuente privada integrada de TourMaps; no
compila ramas de pruebas ni notas del cerebro. Las claves de acceso limitadas
por repositorio y la configuración Android están en secretos cifrados de Actions,
nunca aquí. No contiene ni monta el cerebro personal de ningún colaborador.

Antes de construir respeta la reserva central `release-android`. Una build que
termine tarde no se publica si perdió la reserva o cambió la fuente integrada.
Publica sólo APK piloto, manifest, certificado esperado y hash; las tiendas
requieren su procedimiento independiente. No cambia ni crea firmas de la app.

La firma del piloto +54 no es la firma original de producción. No desinstalar ni
borrar datos para ocultar una incompatibilidad. La prueba física está separada
de las pruebas automáticas y se declara en cada manifest.

El VPS entrega enlaces por el canal existente y verifica el APK independientemente.
Ni los números completos ni las credenciales de WhatsApp están en este repositorio.
El instalador de un PC nuevo sólo necesita la cuenta propia del colaborador y
acceso a los repositorios privados; no necesita copiar claves de compilación.

Reversa: desactivar el workflow detiene nuevas compilaciones; retirar sólo la
línea marcada del cron TourMaps detiene los avisos. Los binarios y recibos previos
se conservan. Una corrección de producto se entrega como una versión superior,
no como un downgrade ni un reset del historial.
