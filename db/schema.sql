--
-- PostgreSQL database dump
--

\restrict bk0pSnCdgpA3gg2tHyF4k1z03PhBlqEbzjKv26W5mMzPMaWmkHbBqSvvQb3iRBv

-- Dumped from database version 15.17 (Homebrew)
-- Dumped by pg_dump version 15.17 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: identity_stats(); Type: FUNCTION; Schema: public
--

CREATE FUNCTION public.identity_stats() RETURNS TABLE(identity_kind text, top_dir text, entries bigint, with_mem_id bigint)
    LANGUAGE sql STABLE
    AS $$
    SELECT identity_kind,
           coalesce(nullif(split_part(vault_path, '/', 1), ''), '(pg-only)') AS top_dir,
           count(*),
           count(mem_id)
    FROM knowledge_identity
    GROUP BY 1, 2
    ORDER BY 1, 2
$$;



--
-- Name: nexus_mem_identity_register(); Type: FUNCTION; Schema: public
--

CREATE FUNCTION public.nexus_mem_identity_register() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    _old_lt TEXT;
BEGIN
    BEGIN
        -- 有界等待：identity 表被锁（回填/维护）时最多阻塞 250ms 即放弃登记，
        -- 保证知识写入主链路延迟不受登记侧拖累。用完恢复事务原值。
        _old_lt := coalesce(current_setting('lock_timeout', true), '0');
        PERFORM set_config('lock_timeout', '250ms', true);
        INSERT INTO knowledge_identity (identity_kind, mem_id, vault_path, producer)
        VALUES ('mem', NEW.id, NEW.path,
                coalesce(nullif(current_setting('app.producer', true), ''),
                         'pg:knowledge-insert'))
        ON CONFLICT DO NOTHING;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'identity register skipped (knowledge %): %', NEW.id, SQLERRM;
    END;
    PERFORM set_config('lock_timeout', _old_lt, true);
    RETURN NEW;
END
$$;



SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _meta; Type: TABLE; Schema: public
--

CREATE TABLE public._meta (
    key character varying(64) NOT NULL,
    value text
);



--
-- Name: agent_activity; Type: TABLE; Schema: public
--

CREATE TABLE public.agent_activity (
    id integer NOT NULL,
    agent_id character varying(32) NOT NULL,
    action character varying(16) NOT NULL,
    target_type character varying(32),
    target_id bigint,
    detail jsonb,
    created timestamp with time zone DEFAULT now(),
    task_id character varying(64),
    injected_pack text,
    outcome character varying(16)
);



--
-- Name: agent_activity_feedback_archive_20260728; Type: TABLE; Schema: public
--

CREATE TABLE public.agent_activity_feedback_archive_20260728 (
    id integer,
    agent_id character varying(32),
    action character varying(16),
    target_type character varying(32),
    target_id bigint,
    detail jsonb,
    created timestamp with time zone,
    task_id character varying(64),
    injected_pack text,
    outcome character varying(16)
);



--
-- Name: agent_activity_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.agent_activity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: agent_activity_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.agent_activity_id_seq OWNED BY public.agent_activity.id;


--
-- Name: agents; Type: TABLE; Schema: public
--

CREATE TABLE public.agents (
    agent_id character varying(32) NOT NULL,
    agent_type character varying(16),
    model character varying(64),
    first_seen timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now(),
    capabilities text[]
);



--
-- Name: credentials; Type: TABLE; Schema: public
--

CREATE TABLE public.credentials (
    credential_id text NOT NULL,
    cred_type text NOT NULL,
    bearer text NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    prerequisites jsonb DEFAULT '{}'::jsonb,
    lease_token bigint NOT NULL,
    signature text NOT NULL,
    status text DEFAULT 'ISSUED'::text,
    task_id text
);



--
-- Name: credentials_lease_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.credentials_lease_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: knowledge; Type: TABLE; Schema: public
--

CREATE TABLE public.knowledge (
    id integer NOT NULL,
    source_agent character varying(32) NOT NULL,
    knowledge_type character varying(32) NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    tags text[],
    project character varying(64),
    path text,
    shadow_code character varying(8),
    confidence double precision DEFAULT 1.0,
    created timestamp with time zone DEFAULT now(),
    updated timestamp with time zone DEFAULT now(),
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, ((COALESCE(title, ''::text) || ' '::text) || COALESCE(content, ''::text)))) STORED,
    embedding public.vector(1024),
    content_hash text,
    verified_at timestamp with time zone,
    entity_type text,
    superseded_by integer,
    decay_factor real DEFAULT 0.0,
    debt_score real DEFAULT 0.0,
    outcome character varying(16),
    task_id character varying(64),
    confidence_source character varying(16) DEFAULT 'llm'::character varying,
    context_coord jsonb,
    deprecated boolean DEFAULT false,
    calibration_weight double precision DEFAULT 1.0,
    ref_count integer DEFAULT 0,
    tokens_zh text,
    search_vector_zh tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, COALESCE(tokens_zh, ''::text))) STORED,
    CONSTRAINT knowledge_type_whitelist CHECK (((knowledge_type)::text = ANY ((ARRAY['document'::character varying, 'experience'::character varying, 'pitfall'::character varying, 'verification'::character varying, 'finding'::character varying, 'counterexample'::character varying, 'memory'::character varying, 'decision'::character varying, 'user_profile'::character varying, 'baseline'::character varying])::text[])))
);



--
-- Name: COLUMN knowledge.superseded_by; Type: COMMENT; Schema: public
--

COMMENT ON COLUMN public.knowledge.superseded_by IS 'task 253 P1-5: 非空=已被该 ID 的新条目取代，检索自动排除';


--
-- Name: knowledge_identity; Type: TABLE; Schema: public
--

CREATE TABLE public.knowledge_identity (
    id bigint NOT NULL,
    identity_kind text NOT NULL,
    mem_id bigint,
    vault_path text,
    producer text DEFAULT 'unknown'::text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    updated timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT knowledge_identity_identity_kind_check CHECK ((identity_kind = ANY (ARRAY['mem'::text, 'vault_doc'::text, 'mirror_shard'::text, 'graph_card'::text, 'index'::text])))
);



--
-- Name: identity_coverage; Type: VIEW; Schema: public
--

CREATE VIEW public.identity_coverage AS
 SELECT ( SELECT count(*) AS count
           FROM public.knowledge) AS knowledge_total,
    ( SELECT count(*) AS count
           FROM public.knowledge_identity
          WHERE (knowledge_identity.identity_kind = 'mem'::text)) AS mem_identity_total,
    ( SELECT count(*) AS count
           FROM public.knowledge
          WHERE (NOT knowledge.deprecated)) AS knowledge_active,
    ( SELECT count(*) AS count
           FROM (public.knowledge_identity i
             JOIN public.knowledge k ON ((k.id = i.mem_id)))
          WHERE ((i.identity_kind = 'mem'::text) AND (NOT k.deprecated))) AS mem_identity_active,
    (( SELECT count(*) AS count
           FROM public.knowledge
          WHERE (NOT knowledge.deprecated)) - ( SELECT count(*) AS count
           FROM (public.knowledge_identity i
             JOIN public.knowledge k ON ((k.id = i.mem_id)))
          WHERE ((i.identity_kind = 'mem'::text) AND (NOT k.deprecated)))) AS active_gap;



--
-- Name: knowledge_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.knowledge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: knowledge_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.knowledge_id_seq OWNED BY public.knowledge.id;


--
-- Name: knowledge_identity_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.knowledge_identity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: knowledge_identity_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.knowledge_identity_id_seq OWNED BY public.knowledge_identity.id;


--
-- Name: knowledge_relation; Type: TABLE; Schema: public
--

CREATE TABLE public.knowledge_relation (
    id bigint NOT NULL,
    src_id bigint NOT NULL,
    dst_id bigint NOT NULL,
    rel_type character varying(16) NOT NULL,
    evidence text,
    created_by character varying(32) DEFAULT 'backfill'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT knowledge_relation_rel_type_check CHECK (((rel_type)::text = ANY (ARRAY[('supersedes'::character varying)::text, ('conflicts'::character varying)::text, ('relates'::character varying)::text, ('provenance'::character varying)::text, ('semantic'::character varying)::text])))
);



--
-- Name: knowledge_relation_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.knowledge_relation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: knowledge_relation_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.knowledge_relation_id_seq OWNED BY public.knowledge_relation.id;


--
-- Name: readmodel_edge; Type: TABLE; Schema: public
--

CREATE TABLE public.readmodel_edge (
    src_identity bigint NOT NULL,
    dst_identity bigint NOT NULL,
    edge_kind text NOT NULL,
    evidence text NOT NULL,
    refresh_id bigint NOT NULL,
    id bigint NOT NULL
);



--
-- Name: readmodel_edge_id_seq; Type: SEQUENCE; Schema: public
--

ALTER TABLE public.readmodel_edge ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.readmodel_edge_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: readmodel_meta; Type: TABLE; Schema: public
--

CREATE TABLE public.readmodel_meta (
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL,
    refresh_id bigint NOT NULL,
    nodes bigint NOT NULL,
    edges bigint NOT NULL,
    edge_kinds jsonb NOT NULL
);



--
-- Name: readmodel_node; Type: TABLE; Schema: public
--

CREATE TABLE public.readmodel_node (
    identity_id bigint NOT NULL,
    kind text NOT NULL,
    mem_id bigint,
    vault_path text,
    refresh_id bigint NOT NULL
);



--
-- Name: readmodel_stats; Type: VIEW; Schema: public
--

CREATE VIEW public.readmodel_stats AS
 SELECT ('node:'::text || readmodel_node.kind) AS metric,
    count(*) AS value
   FROM public.readmodel_node
  GROUP BY readmodel_node.kind
UNION ALL
 SELECT ('edge:'::text || readmodel_edge.edge_kind) AS metric,
    count(*) AS value
   FROM public.readmodel_edge
  GROUP BY readmodel_edge.edge_kind;



--
-- Name: rl_history; Type: TABLE; Schema: public
--

CREATE TABLE public.rl_history (
    id integer NOT NULL,
    step integer,
    code character varying(8),
    layer character(2),
    feedback_type character varying(16),
    feedback_value double precision,
    old_prob double precision,
    new_prob double precision,
    loss double precision,
    created timestamp with time zone DEFAULT now()
);



--
-- Name: rl_history_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.rl_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: rl_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.rl_history_id_seq OWNED BY public.rl_history.id;


--
-- Name: rl_params; Type: TABLE; Schema: public
--

CREATE TABLE public.rl_params (
    param_name character varying(32) NOT NULL,
    value double precision NOT NULL,
    updated timestamp with time zone DEFAULT now()
);



--
-- Name: scheduled_tasks; Type: TABLE; Schema: public
--

CREATE TABLE public.scheduled_tasks (
    name character varying(64) NOT NULL,
    action character varying(16) NOT NULL,
    action_args jsonb DEFAULT '{}'::jsonb NOT NULL,
    interval_sec integer NOT NULL,
    recurring boolean DEFAULT true,
    max_iterations integer,
    expire_at timestamp with time zone,
    last_run_at timestamp with time zone,
    next_run_at timestamp with time zone NOT NULL,
    run_count integer DEFAULT 0,
    last_error text,
    created_at timestamp with time zone DEFAULT now()
);



--
-- Name: session_health; Type: TABLE; Schema: public
--

CREATE TABLE public.session_health (
    id integer NOT NULL,
    event_type character varying(32),
    event_data jsonb,
    token_usage integer,
    created timestamp with time zone DEFAULT now()
);



--
-- Name: session_health_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.session_health_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: session_health_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.session_health_id_seq OWNED BY public.session_health.id;


--
-- Name: shadow_asks; Type: TABLE; Schema: public
--

CREATE TABLE public.shadow_asks (
    id bigint NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    question text NOT NULL,
    context_digest text,
    domain text,
    profile_hits text,
    proxy_answer text,
    proxy_confidence real,
    actual_decision text,
    agree boolean,
    task_ref text,
    closed_at timestamp with time zone
);



--
-- Name: shadow_asks_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.shadow_asks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: shadow_asks_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.shadow_asks_id_seq OWNED BY public.shadow_asks.id;


--
-- Name: shadow_asks_summary; Type: VIEW; Schema: public
--

CREATE VIEW public.shadow_asks_summary AS
 SELECT count(*) AS total_asks,
    count(*) FILTER (WHERE (shadow_asks.closed_at IS NOT NULL)) AS closed_asks,
    count(*) FILTER (WHERE (shadow_asks.agree IS TRUE)) AS agree_count,
    round(COALESCE((((count(*) FILTER (WHERE shadow_asks.agree))::numeric * 100.0) / (NULLIF(count(*) FILTER (WHERE ((shadow_asks.closed_at IS NOT NULL) AND (shadow_asks.agree IS NOT NULL))), 0))::numeric), (0)::numeric), 1) AS agree_rate_pct,
    round((avg(shadow_asks.proxy_confidence))::numeric, 2) AS avg_proxy_confidence,
    (min(shadow_asks.created))::date AS first_ask_date,
    max(shadow_asks.closed_at) AS last_closed_at
   FROM public.shadow_asks;



--
-- Name: shadow_codes; Type: TABLE; Schema: public
--

CREATE TABLE public.shadow_codes (
    code character varying(8) NOT NULL,
    layer character(2) NOT NULL,
    target text NOT NULL,
    section character varying(10),
    ref_count integer DEFAULT 0,
    weight double precision DEFAULT 1.0,
    last_used timestamp with time zone DEFAULT now(),
    created timestamp with time zone DEFAULT now(),
    updated timestamp with time zone DEFAULT now()
);



--
-- Name: tool_calls; Type: TABLE; Schema: public
--

CREATE TABLE public.tool_calls (
    id integer NOT NULL,
    tool_name character varying(128) NOT NULL,
    agent character varying(32) NOT NULL,
    called_at timestamp with time zone DEFAULT now(),
    success boolean,
    duration_ms integer
);



--
-- Name: tool_calls_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.tool_calls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: tool_calls_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.tool_calls_id_seq OWNED BY public.tool_calls.id;


--
-- Name: agent_activity id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.agent_activity ALTER COLUMN id SET DEFAULT nextval('public.agent_activity_id_seq'::regclass);


--
-- Name: knowledge id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.knowledge ALTER COLUMN id SET DEFAULT nextval('public.knowledge_id_seq'::regclass);


--
-- Name: knowledge_identity id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.knowledge_identity ALTER COLUMN id SET DEFAULT nextval('public.knowledge_identity_id_seq'::regclass);


--
-- Name: knowledge_relation id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.knowledge_relation ALTER COLUMN id SET DEFAULT nextval('public.knowledge_relation_id_seq'::regclass);


--
-- Name: rl_history id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.rl_history ALTER COLUMN id SET DEFAULT nextval('public.rl_history_id_seq'::regclass);


--
-- Name: session_health id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.session_health ALTER COLUMN id SET DEFAULT nextval('public.session_health_id_seq'::regclass);


--
-- Name: shadow_asks id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.shadow_asks ALTER COLUMN id SET DEFAULT nextval('public.shadow_asks_id_seq'::regclass);


--
-- Name: tool_calls id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.tool_calls ALTER COLUMN id SET DEFAULT nextval('public.tool_calls_id_seq'::regclass);


--
-- Name: _meta _meta_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public._meta
    ADD CONSTRAINT _meta_pkey PRIMARY KEY (key);


--
-- Name: agent_activity agent_activity_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.agent_activity
    ADD CONSTRAINT agent_activity_pkey PRIMARY KEY (id);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (agent_id);


--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (credential_id);


--
-- Name: knowledge_identity knowledge_identity_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge_identity
    ADD CONSTRAINT knowledge_identity_pkey PRIMARY KEY (id);


--
-- Name: knowledge knowledge_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge
    ADD CONSTRAINT knowledge_pkey PRIMARY KEY (id);


--
-- Name: knowledge_relation knowledge_relation_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge_relation
    ADD CONSTRAINT knowledge_relation_pkey PRIMARY KEY (id);


--
-- Name: readmodel_edge readmodel_edge_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.readmodel_edge
    ADD CONSTRAINT readmodel_edge_pkey PRIMARY KEY (id);


--
-- Name: readmodel_node readmodel_node_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.readmodel_node
    ADD CONSTRAINT readmodel_node_pkey PRIMARY KEY (identity_id);


--
-- Name: rl_history rl_history_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.rl_history
    ADD CONSTRAINT rl_history_pkey PRIMARY KEY (id);


--
-- Name: rl_params rl_params_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.rl_params
    ADD CONSTRAINT rl_params_pkey PRIMARY KEY (param_name);


--
-- Name: scheduled_tasks scheduled_tasks_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.scheduled_tasks
    ADD CONSTRAINT scheduled_tasks_pkey PRIMARY KEY (name);


--
-- Name: session_health session_health_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.session_health
    ADD CONSTRAINT session_health_pkey PRIMARY KEY (id);


--
-- Name: shadow_asks shadow_asks_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.shadow_asks
    ADD CONSTRAINT shadow_asks_pkey PRIMARY KEY (id);


--
-- Name: shadow_codes shadow_codes_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.shadow_codes
    ADD CONSTRAINT shadow_codes_pkey PRIMARY KEY (code);


--
-- Name: tool_calls tool_calls_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.tool_calls
    ADD CONSTRAINT tool_calls_pkey PRIMARY KEY (id);


--
-- Name: knowledge_relation uq_kr_src_dst_type; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge_relation
    ADD CONSTRAINT uq_kr_src_dst_type UNIQUE (src_id, dst_id, rel_type);


--
-- Name: readmodel_edge uq_readmodel_edge_content; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.readmodel_edge
    ADD CONSTRAINT uq_readmodel_edge_content UNIQUE (src_identity, dst_identity, edge_kind, evidence, refresh_id);


--
-- Name: idx_activity_agent; Type: INDEX; Schema: public
--

CREATE INDEX idx_activity_agent ON public.agent_activity USING btree (agent_id);


--
-- Name: idx_knowledge_content_hash_unique; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX idx_knowledge_content_hash_unique ON public.knowledge USING btree (content_hash) WHERE (((knowledge_type)::text <> 'document'::text) AND (superseded_by IS NULL) AND (content_hash IS NOT NULL));


--
-- Name: idx_knowledge_embedding_hnsw; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_embedding_hnsw ON public.knowledge USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_knowledge_fts; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_fts ON public.knowledge USING gin (search_vector);


--
-- Name: idx_knowledge_fts_zh; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_fts_zh ON public.knowledge USING gin (search_vector_zh);


--
-- Name: idx_knowledge_project; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_project ON public.knowledge USING btree (project);


--
-- Name: idx_knowledge_shadow; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_shadow ON public.knowledge USING btree (shadow_code);


--
-- Name: idx_knowledge_tags; Type: INDEX; Schema: public
--

CREATE INDEX idx_knowledge_tags ON public.knowledge USING gin (tags);


--
-- Name: idx_kr_dst_type; Type: INDEX; Schema: public
--

CREATE INDEX idx_kr_dst_type ON public.knowledge_relation USING btree (dst_id, rel_type);


--
-- Name: idx_kr_src_type; Type: INDEX; Schema: public
--

CREATE INDEX idx_kr_src_type ON public.knowledge_relation USING btree (src_id, rel_type);


--
-- Name: idx_rm_edge_dst; Type: INDEX; Schema: public
--

CREATE INDEX idx_rm_edge_dst ON public.readmodel_edge USING btree (dst_identity, edge_kind);


--
-- Name: idx_rm_edge_src; Type: INDEX; Schema: public
--

CREATE INDEX idx_rm_edge_src ON public.readmodel_edge USING btree (src_identity, edge_kind);


--
-- Name: idx_rm_node_kind; Type: INDEX; Schema: public
--

CREATE INDEX idx_rm_node_kind ON public.readmodel_node USING btree (kind);


--
-- Name: idx_rm_node_mem; Type: INDEX; Schema: public
--

CREATE INDEX idx_rm_node_mem ON public.readmodel_node USING btree (mem_id);


--
-- Name: idx_scheduled_tasks_next_run; Type: INDEX; Schema: public
--

CREATE INDEX idx_scheduled_tasks_next_run ON public.scheduled_tasks USING btree (next_run_at);


--
-- Name: idx_shadow_asks_closed; Type: INDEX; Schema: public
--

CREATE INDEX idx_shadow_asks_closed ON public.shadow_asks USING btree (closed_at) WHERE (closed_at IS NOT NULL);


--
-- Name: idx_tool_calls_agent; Type: INDEX; Schema: public
--

CREATE INDEX idx_tool_calls_agent ON public.tool_calls USING btree (agent);


--
-- Name: idx_tool_calls_name; Type: INDEX; Schema: public
--

CREATE INDEX idx_tool_calls_name ON public.tool_calls USING btree (tool_name);


--
-- Name: uq_identity_kind_mem_id; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX uq_identity_kind_mem_id ON public.knowledge_identity USING btree (identity_kind, mem_id) WHERE (mem_id IS NOT NULL);


--
-- Name: uq_identity_kind_vault_path_filekinds; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX uq_identity_kind_vault_path_filekinds ON public.knowledge_identity USING btree (identity_kind, vault_path) WHERE (identity_kind <> 'mem'::text);


--
-- Name: knowledge trg_knowledge_identity_register; Type: TRIGGER; Schema: public
--

CREATE TRIGGER trg_knowledge_identity_register AFTER INSERT ON public.knowledge FOR EACH ROW EXECUTE FUNCTION public.nexus_mem_identity_register();


--
-- Name: knowledge_identity knowledge_identity_mem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge_identity
    ADD CONSTRAINT knowledge_identity_mem_id_fkey FOREIGN KEY (mem_id) REFERENCES public.knowledge(id) ON DELETE CASCADE;


--
-- Name: knowledge knowledge_superseded_by_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.knowledge
    ADD CONSTRAINT knowledge_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES public.knowledge(id);


--
-- PostgreSQL database dump complete
--

\unrestrict bk0pSnCdgpA3gg2tHyF4k1z03PhBlqEbzjKv26W5mMzPMaWmkHbBqSvvQb3iRBv

