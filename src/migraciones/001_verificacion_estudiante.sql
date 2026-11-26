-- =====================================================================
-- Migración 001 - Verificación del estudiante por certificado de alumno regular
--
-- Dónde ejecutarla: Supabase > SQL Editor (en la cuenta/proyecto de Duoc).
-- Es ADITIVA: solo AMPLÍA lo permitido; no borra columnas ni tablas. El
-- backend de DentMatch (la carpeta principal) sigue funcionando igual.
-- Ejecútala UNA vez, ANTES de levantar esta versión contra Supabase.
-- Está dentro de una transacción: si algo falla, no queda nada a medias.
-- =====================================================================

BEGIN;

-- 1) Nuevo estado 'No verificado' en perfil_estudiante.
--    Se busca el CHECK por su contenido (por si su nombre real es otro) y se
--    reemplaza por uno que incluye los 4 estados.
DO $$
DECLARE restriccion record;
BEGIN
  FOR restriccion IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'public.perfil_estudiante'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%estado_verificacion%'
  LOOP
    EXECUTE format('ALTER TABLE public.perfil_estudiante DROP CONSTRAINT %I', restriccion.conname);
  END LOOP;
END $$;

ALTER TABLE public.perfil_estudiante
  ADD CONSTRAINT chk_estado_verificacion
  CHECK (estado_verificacion IN ('No verificado', 'En Verificación', 'Activo', 'Rechazado'));

ALTER TABLE public.perfil_estudiante
  ALTER COLUMN estado_verificacion SET DEFAULT 'No verificado';

-- 2) Historial de certificados subidos.
CREATE TABLE IF NOT EXISTS public.verificaciones_estudiante (
  id                SERIAL PRIMARY KEY,
  estudiante_id     INTEGER NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
  archivo           VARCHAR(255) NOT NULL,
  tipo_contenido    VARCHAR(50)  NOT NULL,
  tamano_bytes      INTEGER      NOT NULL,
  estado            VARCHAR(20)  NOT NULL DEFAULT 'Pendiente',
  motivo            TEXT,
  resuelta_por      VARCHAR(20),
  fecha_subida      TIMESTAMP DEFAULT now(),
  fecha_resolucion  TIMESTAMP,
  CONSTRAINT chk_estado_certificado CHECK (estado IN ('Pendiente', 'Aprobada', 'Rechazada'))
);
CREATE INDEX IF NOT EXISTS ix_verificaciones_estudiante_estudiante_id
  ON public.verificaciones_estudiante (estudiante_id);

-- Seguridad: Supabase expone por API pública las tablas de `public`. Con RLS activado
-- y SIN políticas, nadie puede leerla con la clave pública; el backend (que se conecta
-- directo a Postgres) no se ve afectado.
ALTER TABLE public.verificaciones_estudiante ENABLE ROW LEVEL SECURITY;

-- 3) Bucket PRIVADO para los certificados (contienen nombre y RUT).
--    Sin políticas, solo el backend con la clave de servicio puede leer o escribir.
INSERT INTO storage.buckets (id, name, public)
VALUES ('certificados', 'certificados', false)
ON CONFLICT (id) DO NOTHING;

-- 4) Estudiantes ya registrados: ninguno ha subido certificado todavía, así que pasan a
--    'No verificado' (incluso los que estaban 'Activo' sin documento). Los que ya tenían un
--    archivo en certificado_documento no se tocan.
UPDATE public.perfil_estudiante
SET estado_verificacion = 'No verificado'
WHERE certificado_documento IS NULL;

COMMIT;

-- Para comprobar el resultado:
--   SELECT estado_verificacion, count(*) FROM public.perfil_estudiante GROUP BY 1;
--   SELECT id, public FROM storage.buckets WHERE id = 'certificados';
