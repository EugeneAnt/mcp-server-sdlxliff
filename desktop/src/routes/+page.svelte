<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Header from '$lib/components/Header.svelte';
	import FileBar from '$lib/components/FileBar.svelte';
	import StatusLine from '$lib/components/StatusLine.svelte';
	import FileSelector from '$lib/components/FileSelector.svelte';
	import ChatView from '$lib/components/ChatView.svelte';
	import ToolsPanel from '$lib/components/ToolsPanel.svelte';
	import IssuesPanel from '$lib/components/IssuesPanel.svelte';
	import Composer from '$lib/components/Composer.svelte';
	import ApiKeyDialog from '$lib/components/ApiKeyDialog.svelte';
	import { initializeApp, cleanupApp, setScrollCallbacks } from '$lib/services/chatService';
	import { showApiKeyInput } from '$lib/stores/settings';
	import { sessionIssues } from '$lib/stores/issues';
	
	let chatView: ChatView;
	let toolsPanel: ToolsPanel;

	onMount(() => {
		initializeApp();
		// Set up scroll callbacks for tool calls
		setScrollCallbacks(
			() => chatView?.scrollToBottom(),
			() => toolsPanel?.scrollToBottom()
		);
	});

	onDestroy(() => {
		cleanupApp();
	});
</script>

<div class="flex flex-col h-screen bg-zinc-900 text-zinc-200 font-sans">
	<Header />
	<FileBar />
	<StatusLine />
	<FileSelector />

	<main class="flex-1 flex overflow-hidden relative">
		{#if $showApiKeyInput}
			<ApiKeyDialog />
		{:else}
			<div class="flex-1 flex">
				<div class="flex-1 flex flex-col min-w-0 border-r border-zinc-700">
					<ChatView bind:this={chatView} />
					<Composer />
				</div>
				<ToolsPanel bind:this={toolsPanel} />
				<!-- Always mount IssuesPanel to avoid render freeze when issues arrive -->
				<IssuesPanel hidden={$sessionIssues.length === 0} />
			</div>

		{/if}
	</main>
</div>
