-- =====================================================================
-- Migración 002 - Vigencia semestral del certificado de alumno regular
--
-- Dónde ejecutarla: Supabase > SQL Editor (mismo proyecto que la 001).
-- Es ADITIVA: solo agrega una columna opcional a TU tabla verificaciones_estudiante.
-- Ejecútala UNA vez, ANTES de levantar esta versión contra Supabase (sin ella,
-- subir un certificado falla porque el backend escribe esta columna).
-- =====================================================================

ALTER TABLE public.verificaciones_estudiante
  ADD COLUMN IF NOT EXISTS fecha_emision DATE;

-- Los certificados ya aprobados quedan sin fecha de emisión: el backend usa entonces la
-- fecha en que se subieron para calcular el semestre.
