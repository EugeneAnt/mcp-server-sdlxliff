import { writable } from 'svelte/store';
import { load, type Store } from '@tauri-apps/plugin-store';

// UI state for API key input
export const apiKey = writable('');
export const showApiKeyInput = writable(true);

// RAG settings
export const ragEnabled = writable(false);
export const ragUseOllama = writable(false);
export const openaiApiKey = writable('');

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

// RAG settings persistence
export async function getRagSettings(): Promise<{
	enabled: boolean;
	useOllama: boolean;
	openaiKey: string | null;
}> {
	const s = await getStore();
	return {
		enabled: (await s.get<boolean>('ragEnabled')) ?? false,
		useOllama: (await s.get<boolean>('ragUseOllama')) ?? false,
		openaiKey: (await s.get<string>('openaiApiKey')) ?? null
	};
}

export async function setRagSettings(settings: {
	enabled: boolean;
	useOllama: boolean;
	openaiKey?: string;
}): Promise<void> {
	const s = await getStore();
	await s.set('ragEnabled', settings.enabled);
	await s.set('ragUseOllama', settings.useOllama);
	if (settings.openaiKey !== undefined) {
		await s.set('openaiApiKey', settings.openaiKey);
	}
}
