-- =====================================================================
-- Migración 004 - Archivar conversaciones del chat
--
-- Dónde ejecutarla: Supabase > SQL Editor (mismo proyecto que las migraciones anteriores).
-- Es ADITIVA: solo CREA una tabla nueva; no toca ninguna existente.
-- Se puede ejecutar más de una vez sin problema (IF NOT EXISTS).
--
-- (Si no se ejecuta, el backend crea esta misma tabla solo al arrancar.)
-- =====================================================================

BEGIN;

-- Una de las dos personas archivó el chat de una postulación: queda de solo lectura y solo
-- quien lo archivó puede reabrirlo. No cambia la postulación ni las citas.
CREATE TABLE IF NOT EXISTS public.conversaciones_archivadas (
  postulacion_id  INTEGER PRIMARY KEY REFERENCES public.postulaciones(id) ON DELETE CASCADE,
  archivada_por   INTEGER NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
  fecha           TIMESTAMP NOT NULL
);

COMMIT;
