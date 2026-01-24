<script lang="ts">
	import { ragEnabled, ragUseOllama, openaiApiKey } from '$lib/stores/settings';
	import {
		setRagEnabled,
		updateRagProvider,
		ragInitialized,
		ragIndexing,
		ragError
	} from '$lib/services/ragService';
	import { checkOllama, checkOllamaModel, installOllama, startOllama, pullOllamaModel as pullModel } from '$lib/rag';

	let showSettings = false;
	let localOpenaiKey = '';
	let saving = false;
	let pullingModel = false;
	let ollamaRunning = false;
	let modelInstalled = false;
	let installing = false;
	let starting = false;
	let statusMessage = '';

	// Sync local state
	$: localOpenaiKey = $openaiApiKey;

	// Check Ollama status when settings open
	$: if (showSettings && $ragUseOllama) {
		refreshOllamaStatus();
	}

	async function refreshOllamaStatus() {
		ollamaRunning = await checkOllama();
		if (ollamaRunning) {
			modelInstalled = await checkOllamaModel('nomic-embed-text');
		}
	}

	async function handleInstallOllama() {
		installing = true;
		statusMessage = '';
		try {
			const result = await installOllama();
			statusMessage = result;
		} catch (error) {
			statusMessage = error instanceof Error ? error.message : 'Failed to install';
		}
		installing = false;
	}

	async function handleStartOllama() {
		starting = true;
		statusMessage = '';
		try {
			const result = await startOllama();
			statusMessage = result;
			// Wait a bit then check status
			setTimeout(refreshOllamaStatus, 3000);
		} catch (error) {
			statusMessage = error instanceof Error ? error.message : 'Failed to start';
		}
		starting = false;
	}

	async function toggleRag() {
		saving = true;
		statusMessage = '';
		try {
			await setRagEnabled(!$ragEnabled);
		} catch (error) {
			statusMessage = error instanceof Error ? error.message : 'Failed to toggle RAG';
		}
		saving = false;
	}

	async function saveProvider() {
		saving = true;
		statusMessage = '';
		try {
			await updateRagProvider($ragUseOllama, localOpenaiKey);
			statusMessage = 'Settings saved';
			setTimeout(() => (showSettings = false), 1000);
		} catch (error) {
			statusMessage = error instanceof Error ? error.message : 'Failed to save settings';
		}
		saving = false;
	}

	async function pullOllamaModel() {
		pullingModel = true;
		statusMessage = 'Pulling model (this may take a minute)...';
		try {
			const result = await pullModel('nomic-embed-text');
			statusMessage = result;
			modelInstalled = true;
		} catch (error) {
			statusMessage = error instanceof Error ? error.message : 'Failed to pull model';
		}
		pullingModel = false;
	}
</script>

<div class="relative">
	<button
		onclick={() => (showSettings = !showSettings)}
		class="flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors
			{$ragEnabled && $ragInitialized
			? 'bg-green-900/50 text-green-400'
			: $ragEnabled
				? 'bg-amber-900/50 text-amber-400'
				: 'bg-zinc-700/50 text-zinc-400'}
			hover:bg-zinc-600"
		title={$ragEnabled && $ragInitialized
			? 'RAG ready'
			: $ragEnabled
				? 'RAG enabled but not ready'
				: 'RAG disabled'}
	>
		<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
			/>
		</svg>
		<span>RAG</span>
		{#if $ragIndexing}
			<span class="text-amber-400 animate-pulse">...</span>
		{/if}
	</button>

	{#if showSettings}
		<div
			class="absolute right-0 top-full mt-1 w-72 bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl z-50 p-4"
		>
			<div class="flex justify-between items-center mb-3">
				<h3 class="text-sm font-medium text-zinc-200">RAG Settings</h3>
				<button onclick={() => (showSettings = false)} class="text-zinc-400 hover:text-zinc-200" title="Close">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						/>
					</svg>
				</button>
			</div>

			<div class="space-y-3">
				<!-- Enable toggle -->
				<label class="flex items-center gap-2 cursor-pointer">
					<input
						type="checkbox"
						checked={$ragEnabled}
						onchange={toggleRag}
						disabled={saving}
						class="w-4 h-4 rounded bg-zinc-700 border-zinc-600"
					/>
					<span class="text-sm text-zinc-300">Enable RAG</span>
					{#if $ragInitialized}
						<span class="text-xs text-green-400">Active</span>
					{/if}
				</label>

				<!-- Provider selection -->
				<div class="space-y-2">
					<label class="flex items-center gap-2 cursor-pointer">
						<input
							type="radio"
							name="provider"
							checked={!$ragUseOllama}
							onchange={() => ragUseOllama.set(false)}
							class="w-4 h-4 bg-zinc-700 border-zinc-600"
						/>
						<span class="text-sm text-zinc-300">OpenAI</span>
					</label>

					<label class="flex items-center gap-2 cursor-pointer">
						<input
							type="radio"
							name="provider"
							checked={$ragUseOllama}
							onchange={() => ragUseOllama.set(true)}
							class="w-4 h-4 bg-zinc-700 border-zinc-600"
						/>
						<span class="text-sm text-zinc-300">Ollama (local)</span>
					</label>
				</div>

				<!-- OpenAI key input -->
				{#if !$ragUseOllama}
					<div>
						<label for="openai-key" class="block text-xs text-zinc-400 mb-1">OpenAI API Key</label>
						<input
							id="openai-key"
							type="password"
							bind:value={localOpenaiKey}
							placeholder="sk-..."
							class="w-full px-2 py-1 text-sm bg-zinc-700 border border-zinc-600 rounded text-zinc-200 placeholder-zinc-500"
						/>
					</div>
				{:else}
					<div class="space-y-2">
						<div class="flex items-center justify-between text-xs">
							<div class="flex items-center gap-2">
								<span class="w-2 h-2 rounded-full {ollamaRunning ? 'bg-green-500' : 'bg-red-500'}"></span>
								<span class="text-zinc-400">
									Ollama: {ollamaRunning ? 'running' : 'not running'}
								</span>
							</div>
							<button
								onclick={refreshOllamaStatus}
								class="text-zinc-500 hover:text-zinc-300"
								title="Refresh status"
							>
								<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
							</button>
						</div>
						{#if !ollamaRunning}
							<div class="flex gap-2">
								<button
									onclick={handleInstallOllama}
									disabled={installing}
									class="flex-1 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 text-zinc-300 rounded transition-colors"
								>
									{installing ? 'Installing...' : '1. Install'}
								</button>
								<button
									onclick={handleStartOllama}
									disabled={starting}
									class="flex-1 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 text-zinc-300 rounded transition-colors"
								>
									{starting ? 'Starting...' : '2. Start'}
								</button>
							</div>
						{/if}
						{#if modelInstalled}
						<div class="flex items-center gap-2 text-xs text-green-400">
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
							</svg>
							<span>nomic-embed-text installed</span>
						</div>
						{:else}
						<button
							onclick={pullOllamaModel}
							disabled={pullingModel || !ollamaRunning}
							class="w-full py-1 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-300 rounded transition-colors"
						>
							{pullingModel ? 'Pulling model...' : '3. Install embedding model'}
						</button>
						{/if}
					</div>
				{/if}

				<!-- Status/Error display -->
				{#if statusMessage}
					<p class="text-xs text-blue-400">{statusMessage}</p>
				{/if}
				{#if $ragError}
					<p class="text-xs text-red-400">{$ragError}</p>
				{/if}

				<!-- Save button -->
				<button
					onclick={saveProvider}
					disabled={saving}
					class="w-full py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-600 text-white rounded transition-colors"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	{/if}
</div>