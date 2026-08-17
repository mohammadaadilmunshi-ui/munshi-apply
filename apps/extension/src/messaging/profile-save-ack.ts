export type ProfileSaveConflictDetail = {
  key: string;
  localValue: unknown;
  remoteValue: unknown;
};

export type ProfileSaveConflict = {
  keys: string[];
  details: ProfileSaveConflictDetail[];
  detectedAt: string;
};

export type ProfileSaveAck = {
  localSaved: true;
  cloudSynced: boolean;
  conflict: ProfileSaveConflict | null;
};

export function localProfileSaveAck(
  conflict: ProfileSaveConflict | null = null,
): ProfileSaveAck {
  return {
    localSaved: true,
    cloudSynced: false,
    conflict,
  };
}

export function syncedProfileSaveAck(): ProfileSaveAck {
  return {
    localSaved: true,
    cloudSynced: true,
    conflict: null,
  };
}

export function parseProfileSaveAck(value: unknown): ProfileSaveAck {
  if (!value || typeof value !== "object") {
    throw new Error("Profile save returned no acknowledgement");
  }
  const candidate = value as Partial<ProfileSaveAck>;
  if (candidate.localSaved !== true || typeof candidate.cloudSynced !== "boolean") {
    throw new Error("Profile save acknowledgement is invalid");
  }
  if (candidate.cloudSynced && candidate.conflict) {
    throw new Error("Profile save cannot be synced while a conflict is unresolved");
  }
  return {
    localSaved: true,
    cloudSynced: candidate.cloudSynced,
    conflict: candidate.conflict ?? null,
  };
}
