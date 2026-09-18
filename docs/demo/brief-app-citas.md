# Brief: App de citas — Talleres Norte

Documento ficticio para la demo de Jarvis (`docs/DEMO.md`).

## Cliente

Talleres Norte es una cadena de tres talleres mecánicos. Hoy las citas se piden por
teléfono y se apuntan en una hoja de cálculo compartida; en temporada alta se pierden
citas y los clientes esperan hasta 20 minutos al teléfono.

## Objetivo

Una aplicación web (adaptada al móvil) para que el cliente reserve cita en el taller que
elija, vea el estado de su vehículo y reciba un recordatorio por correo el día anterior.

## Alcance

* Reserva de cita por taller, servicio (revisión, neumáticos, ITV, avería) y franja horaria.
* Panel para el personal del taller: citas del día, cambio de estado del vehículo.
* Recordatorio por correo 24 horas antes.
* Fuera de alcance: pagos online y app nativa de iOS/Android.

## Presupuesto y plazos

* Presupuesto: 18.000 € (IVA no incluido).
* Duración: 10 semanas. Salida a producción antes del inicio de la campaña de invierno.

## Criterios de aceptación

1. Un cliente reserva una cita en menos de 2 minutos desde el móvil.
2. El taller ve la cita al instante en su panel.
3. El 95 % de los recordatorios se entregan sin caer en spam.

## Riesgos conocidos

* Los tres talleres usan horarios distintos y no están documentados.
* El proveedor actual de correo del cliente no tiene configurado SPF/DKIM.
