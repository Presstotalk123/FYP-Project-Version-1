-- Reference PostgreSQL DDL for Database Rescue.
-- Upgrade with python run_competition_migration.py; never reset existing tables.
CREATE TABLE IF NOT EXISTS competition_execution_leases (
	user_id INTEGER NOT NULL, 
	token VARCHAR(40) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS competition_sources (
	id SERIAL NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	external_id VARCHAR(100) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	snapshot JSON NOT NULL, 
	diagnostics JSON NOT NULL, 
	authorised INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (provider, external_id, content_hash), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS competitions (
	id SERIAL NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	topic VARCHAR(100) NOT NULL, 
	config JSON NOT NULL, 
	published INTEGER NOT NULL, 
	content_hash VARCHAR(64), 
	opens_at TIMESTAMP WITH TIME ZONE, 
	closes_at TIMESTAMP WITH TIME ZONE, 
	feedback_released INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS competition_incidents (
	id SERIAL NOT NULL, 
	origin_key VARCHAR(100), 
	source_id INTEGER, 
	title VARCHAR(255) NOT NULL, 
	document JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	revision INTEGER NOT NULL, 
	validation JSON, 
	validated_hash VARCHAR(64), 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (origin_key), 
	FOREIGN KEY(source_id) REFERENCES competition_sources (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS competition_participations (
	id SERIAL NOT NULL, 
	competition_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	cohort VARCHAR(100) NOT NULL, 
	form_order VARCHAR(2) NOT NULL, 
	phase VARCHAR(20) NOT NULL, 
	phase_active INTEGER NOT NULL, 
	pre_submitted_at TIMESTAMP WITH TIME ZONE, 
	post_submitted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (competition_id, user_id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_participations_competition_id ON competition_participations (competition_id);

CREATE INDEX IF NOT EXISTS ix_competition_participations_user_id ON competition_participations (user_id);

CREATE TABLE IF NOT EXISTS competition_drafts (
	id SERIAL NOT NULL, 
	participation_id INTEGER NOT NULL, 
	item_key VARCHAR(40) NOT NULL, 
	revision INTEGER NOT NULL, 
	payload JSON NOT NULL, 
	help_level INTEGER NOT NULL, 
	submitted INTEGER NOT NULL, 
	restored INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (participation_id, item_key), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id)
);

CREATE TABLE IF NOT EXISTS competition_events (
	id SERIAL NOT NULL, 
	participation_id INTEGER NOT NULL, 
	item_key VARCHAR(40), 
	event_type VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_events_participation_id ON competition_events (participation_id);

CREATE TABLE IF NOT EXISTS competition_incident_versions (
	id SERIAL NOT NULL, 
	incident_id INTEGER NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	document JSON NOT NULL, 
	source_id INTEGER, 
	parser_version VARCHAR(100) NOT NULL, 
	approved_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (incident_id, content_hash), 
	FOREIGN KEY(incident_id) REFERENCES competition_incidents (id), 
	FOREIGN KEY(source_id) REFERENCES competition_sources (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS competition_runs (
	id SERIAL NOT NULL, 
	participation_id INTEGER NOT NULL, 
	item_key VARCHAR(40) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	component_id VARCHAR(60), 
	sql TEXT NOT NULL, 
	result JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_runs_participation_id ON competition_runs (participation_id);

CREATE TABLE IF NOT EXISTS competition_surveys (
	participation_id INTEGER NOT NULL, 
	response JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (participation_id), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id)
);

CREATE TABLE IF NOT EXISTS competition_submissions (
	id SERIAL NOT NULL, 
	participation_id INTEGER NOT NULL, 
	item_key VARCHAR(40) NOT NULL, 
	request_key VARCHAR(80) NOT NULL, 
	incident_version_id INTEGER NOT NULL, 
	draft_revision INTEGER NOT NULL, 
	payload JSON NOT NULL, 
	help_level INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	result JSON, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	graded_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (participation_id, request_key), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id), 
	FOREIGN KEY(incident_version_id) REFERENCES competition_incident_versions (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_submissions_participation_id ON competition_submissions (participation_id);

CREATE TABLE IF NOT EXISTS competition_reviews (
	id SERIAL NOT NULL, 
	submission_id INTEGER NOT NULL, 
	diagnosis_score INTEGER NOT NULL, 
	explanation_score INTEGER NOT NULL, 
	rationale TEXT NOT NULL, 
	rubric_version VARCHAR(30) NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(submission_id) REFERENCES competition_submissions (id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_reviews_submission_id ON competition_reviews (submission_id);

CREATE TABLE IF NOT EXISTS competition_rewards (
	id SERIAL NOT NULL, 
	participation_id INTEGER NOT NULL, 
	item_key VARCHAR(40) NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	xp INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (participation_id, item_key, kind), 
	FOREIGN KEY(participation_id) REFERENCES competition_participations (id), 
	FOREIGN KEY(submission_id) REFERENCES competition_submissions (id)
);

CREATE INDEX IF NOT EXISTS ix_competition_rewards_participation_id ON competition_rewards (participation_id);
