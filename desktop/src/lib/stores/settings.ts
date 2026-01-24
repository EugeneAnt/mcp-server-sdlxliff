import { writable } from 'svelte/store';
import { load, type Store } from '@tauri-apps/plugin-store';

// UI state for API key input
export const apiKey = writable('');
export const showApiKeyInput = writable(true);

// Store instance (lazy loaded)
let store: Store | null = null;

async function getStore(): Promise<Store> {
	if (!store) {
		store = await load('settings.json', {
			defaults: {},
			autoSave: true
		});
	}
	return store;
}

export async function getApiKey(): Promise<string | null> {
	const s = await getStore();
	return (await s.get<string>('anthropicApiKey')) ?? null;
}

export async function setApiKey(key: string): Promise<void> {
	const s = await getStore();
	await s.set('anthropicApiKey', key);
}

export async function clearApiKey(): Promise<void> {
	const s = await getStore();
	await s.delete('anthropicApiKey');
}
