-- =====================================================================
-- Migración 003 - Moderación del chat (Épica 5)
--
-- Dónde ejecutarla: Supabase > SQL Editor (mismo proyecto que las migraciones 001 y 002).
-- Es ADITIVA: solo CREA 5 tablas nuevas; no toca ninguna tabla existente.
-- Se puede ejecutar más de una vez sin problema (IF NOT EXISTS).
-- Está dentro de una transacción: si algo falla, no queda nada a medias.
--
-- (Si no se ejecuta, el backend crea estas mismas tablas solo al arrancar; este script
--  sirve para dejarlas listas y con la seguridad activada desde antes.)
-- =====================================================================

BEGIN;

-- Sanción vigente de una cuenta. Sin fila = cuenta activa.
CREATE TABLE IF NOT EXISTS public.estado_cuenta (
  usuario_id        INTEGER PRIMARY KEY REFERENCES public.usuarios(id) ON DELETE CASCADE,
  estado            VARCHAR(20) NOT NULL DEFAULT 'activo',
  suspendido_hasta  TIMESTAMP,
  motivo            TEXT,
  actualizado_en    TIMESTAMP,
  CONSTRAINT chk_estado_cuenta CHECK (estado IN ('activo', 'suspendido', 'baneado'))
);

-- Mensajes bloqueados por la moderación (no llegan a la otra persona). Sirven de evidencia.
CREATE TABLE IF NOT EXISTS public.advertencias (
  id                SERIAL PRIMARY KEY,
  usuario_id        INTEGER NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
  postulacion_id    INTEGER REFERENCES public.postulaciones(id) ON DELETE CASCADE,
  categoria         VARCHAR(20) NOT NULL,
  fuente            VARCHAR(10) NOT NULL,
  contenido         TEXT NOT NULL,
  cuenta            BOOLEAN NOT NULL DEFAULT TRUE,
  receptor_avisado  BOOLEAN NOT NULL DEFAULT FALSE,
  fecha             TIMESTAMP NOT NULL,
  CONSTRAINT chk_categoria_advertencia CHECK (categoria IN ('insulto', 'acoso', 'fuera_de_tema'))
);
CREATE INDEX IF NOT EXISTS ix_advertencias_usuario_id    ON public.advertencias (usuario_id);
CREATE INDEX IF NOT EXISTS ix_advertencias_postulacion_id ON public.advertencias (postulacion_id);

-- Reportes de conducta (de una persona o automáticos al llegar a 3 advertencias).
-- Guardan una copia de la conversación como evidencia.
CREATE TABLE IF NOT EXISTS public.reportes (
  id                SERIAL PRIMARY KEY,
  postulacion_id    INTEGER REFERENCES public.postulaciones(id) ON DELETE SET NULL,
  reportante_id     INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
  reportado_id      INTEGER NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
  origen            VARCHAR(15) NOT NULL,
  motivo            TEXT NOT NULL,
  evidencia         TEXT,
  estado            VARCHAR(15) NOT NULL DEFAULT 'Pendiente',
  decision          VARCHAR(15),
  nota_admin        TEXT,
  suspension_dias   INTEGER,
  resuelto_por      INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
  fecha_creacion    TIMESTAMP NOT NULL,
  fecha_resolucion  TIMESTAMP,
  CONSTRAINT chk_estado_reporte   CHECK (estado IN ('Pendiente', 'Resuelto')),
  CONSTRAINT chk_origen_reporte   CHECK (origen IN ('usuario', 'automatico')),
  CONSTRAINT chk_decision_reporte CHECK (decision IS NULL OR decision IN ('baneo', 'suspension', 'descartar'))
);
CREATE INDEX IF NOT EXISTS ix_reportes_reportado_id ON public.reportes (reportado_id);

-- Avisos cortos para una persona (ej. "el chat fue detenido"). Se muestran una sola vez.
CREATE TABLE IF NOT EXISTS public.avisos_usuario (
  id          SERIAL PRIMARY KEY,
  usuario_id  INTEGER NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
  texto       TEXT NOT NULL,
  fecha       TIMESTAMP NOT NULL,
  leido_en    TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_avisos_usuario_usuario_id ON public.avisos_usuario (usuario_id);

-- Conversaciones detenidas por la moderación (la otra persona ve un mensaje explicándolo).
CREATE TABLE IF NOT EXISTS public.cierres_moderacion (
  postulacion_id  INTEGER PRIMARY KEY REFERENCES public.postulaciones(id) ON DELETE CASCADE,
  fecha           TIMESTAMP NOT NULL
);

-- Nota: no se activa RLS (el proyecto no lo usa en sus otras tablas y antes dio problemas).
-- Las tablas quedan como las demás del proyecto.

COMMIT;
