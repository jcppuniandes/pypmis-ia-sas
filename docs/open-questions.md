# Preguntas abiertas

## Organización y Seguridad — Nivel 1

1. ¿La identidad de usuario debe convertirse inmediatamente en global entre empresas o se mantiene temporalmente `UserAccount` por tenant hasta migrar los datos existentes?
2. ¿El alta de nuevas empresas se habilitará desde la misma aplicación o mediante un bootstrap separado reservado a `platform_admin`?
3. ¿Qué proveedor de correo se utilizará para invitaciones y recuperación de contraseña en producción?
4. ¿Cuál es la vigencia objetivo del access token y del refresh token para los ambientes piloto y productivo?
5. ¿Los roles de sistema podrán personalizar permisos por empresa o permanecerán completamente bloqueados por seed?
6. ¿Qué unidades organizacionales iniciales deben crearse automáticamente para cada nueva empresa?
7. ¿Se exige RLS en todas las tablas tenant-scoped antes del primer piloto de esta etapa o se desplegará detrás de una bandera de migración?

