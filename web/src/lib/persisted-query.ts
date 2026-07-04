const STORAGE_PREFIX = "xirang:query:v1:";

export interface PersistedQuerySnapshot<T> {
  data: T;
  updatedAt: number;
}

interface PersistedQueryEnvelope<T> extends PersistedQuerySnapshot<T> {
  version: 1;
}

export function persistedQueryStorageKey(key: string): string {
  return `${STORAGE_PREFIX}${key}`;
}

export function readPersistedQuery<T>(
  key: string,
  options: { maxAgeMs: number; now?: number; storage?: Storage },
): PersistedQuerySnapshot<T> | undefined {
  const storage = options.storage ?? browserStorage();
  if (!storage) {
    return undefined;
  }

  const storageKey = persistedQueryStorageKey(key);
  const raw = storage.getItem(storageKey);
  if (!raw) {
    return undefined;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PersistedQueryEnvelope<T>>;
    if (parsed.version !== 1 || typeof parsed.updatedAt !== "number" || !("data" in parsed)) {
      storage.removeItem(storageKey);
      return undefined;
    }
    if ((options.now ?? Date.now()) - parsed.updatedAt > options.maxAgeMs) {
      storage.removeItem(storageKey);
      return undefined;
    }
    return { data: parsed.data as T, updatedAt: parsed.updatedAt };
  } catch {
    storage.removeItem(storageKey);
    return undefined;
  }
}

export function writePersistedQuery<T>(
  key: string,
  data: T,
  updatedAt = Date.now(),
  storage = browserStorage(),
): void {
  if (!storage) {
    return;
  }

  try {
    const envelope: PersistedQueryEnvelope<T> = { version: 1, data, updatedAt };
    storage.setItem(persistedQueryStorageKey(key), JSON.stringify(envelope));
  } catch {
    clearPersistedQuery(key, storage);
  }
}

export function clearPersistedQuery(key: string, storage = browserStorage()): void {
  storage?.removeItem(persistedQueryStorageKey(key));
}

function browserStorage(): Storage | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
