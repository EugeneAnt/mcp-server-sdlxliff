import { writable, derived } from 'svelte/store';
import type { ModelChoice } from '$lib/claude';

export const selectedModel = writable<ModelChoice>('sonnet');
export const currentModelUsed = writable<string | null>(null);

// Derived store for display name
export const currentModelDisplayName = derived(currentModelUsed, ($model) => {
	if (!$model) return null;
	if ($model.includes('haiku')) return 'Haiku';
	if ($model.includes('sonnet')) return 'Sonnet';
	return $model;
});
