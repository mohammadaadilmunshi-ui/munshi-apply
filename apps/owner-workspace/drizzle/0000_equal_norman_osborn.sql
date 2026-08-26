CREATE TABLE `conflicts` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`entity_type` text NOT NULL,
	`entity_id` text NOT NULL,
	`incoming_event_id` text NOT NULL,
	`correlation_id` text NOT NULL,
	`schema_version` text NOT NULL,
	`payload_ciphertext` text NOT NULL,
	`payload_sha256` text NOT NULL,
	`expected_version` integer NOT NULL,
	`received_base_version` integer NOT NULL,
	`status` text DEFAULT 'OPEN' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`resolved_at` text,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `conflicts_workspace_status` ON `conflicts` (`workspace_id`,`status`);--> statement-breakpoint
CREATE UNIQUE INDEX `conflicts_incoming_event` ON `conflicts` (`incoming_event_id`);--> statement-breakpoint
CREATE TABLE `devices` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`pairing_challenge_id` text NOT NULL,
	`label_ciphertext` text NOT NULL,
	`platform` text NOT NULL,
	`public_key_jwk` text NOT NULL,
	`credential_sha256` text NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`last_seen_at` text,
	`revoked_at` text,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`pairing_challenge_id`) REFERENCES `pairing_challenges`(`id`) ON UPDATE no action ON DELETE restrict
);
--> statement-breakpoint
CREATE INDEX `devices_workspace` ON `devices` (`workspace_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `devices_pairing_challenge` ON `devices` (`pairing_challenge_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `devices_credential` ON `devices` (`credential_sha256`);--> statement-breakpoint
CREATE TABLE `encrypted_objects` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`object_key` text NOT NULL,
	`purpose` text NOT NULL,
	`metadata_ciphertext` text NOT NULL,
	`wrapped_key` text NOT NULL,
	`payload_sha256` text NOT NULL,
	`size_bytes` integer NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `encrypted_objects_workspace` ON `encrypted_objects` (`workspace_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `encrypted_objects_key` ON `encrypted_objects` (`object_key`);--> statement-breakpoint
CREATE TABLE `entity_versions` (
	`workspace_id` text NOT NULL,
	`entity_type` text NOT NULL,
	`entity_id` text NOT NULL,
	`current_version` integer NOT NULL,
	`last_event_id` text NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY(`workspace_id`, `entity_type`, `entity_id`),
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `pairing_challenges` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`secret_sha256` text NOT NULL,
	`expires_at` text NOT NULL,
	`used_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `pairing_challenges_workspace` ON `pairing_challenges` (`workspace_id`);--> statement-breakpoint
CREATE TABLE `sync_events` (
	`sequence` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`id` text NOT NULL,
	`workspace_id` text NOT NULL,
	`device_id` text,
	`correlation_id` text NOT NULL,
	`entity_type` text NOT NULL,
	`entity_id` text NOT NULL,
	`base_version` integer NOT NULL,
	`schema_version` text NOT NULL,
	`payload_ciphertext` text NOT NULL,
	`payload_sha256` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspaces`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`device_id`) REFERENCES `devices`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `sync_events_event_id` ON `sync_events` (`id`);--> statement-breakpoint
CREATE INDEX `sync_events_workspace_created` ON `sync_events` (`workspace_id`,`created_at`);--> statement-breakpoint
CREATE INDEX `sync_events_entity` ON `sync_events` (`workspace_id`,`entity_type`,`entity_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `sync_events_entity_version_slot` ON `sync_events` (`workspace_id`,`entity_type`,`entity_id`,`base_version`);--> statement-breakpoint
CREATE TABLE `workspaces` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_email` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `workspaces_owner_email` ON `workspaces` (`owner_email`);