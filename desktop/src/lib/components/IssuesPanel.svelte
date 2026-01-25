<script lang="ts">
	import {
		sessionIssues,
		resolveIssue,
		unresolveIssue,
		exportAsMarkdown,
		exportAsCsv,
		type Issue
	} from '$lib/stores/issues';

	let expandedTypes: Set<string> = new Set();
	let showExportMenu = false;

	// Group issues by type
	$: issuesByType = $sessionIssues.reduce(
		(acc, issue) => {
			const list = acc.get(issue.issue_type) || [];
			list.push(issue);
			acc.set(issue.issue_type, list);
			return acc;
		},
		new Map<string, Issue[]>()
	);

	$: unresolvedCount = $sessionIssues.filter((i) => !i.resolved).length;
	$: totalCount = $sessionIssues.length;

	function toggleType(type: string) {
		if (expandedTypes.has(type)) {
			expandedTypes.delete(type);
		} else {
			expandedTypes.add(type);
		}
		expandedTypes = expandedTypes; // trigger reactivity
	}

	function formatType(type: string): string {
		return type
			.replace(/^qa_/, '')
			.replace(/_/g, ' ')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	function getSeverityColor(severity: string): string {
		switch (severity) {
			case 'error':
				return 'text-red-400 bg-red-900/30';
			case 'warning':
				return 'text-yellow-400 bg-yellow-900/30';
			case 'info':
				return 'text-blue-400 bg-blue-900/30';
			default:
				return 'text-zinc-400 bg-zinc-800';
		}
	}

	function getTypeColor(type: string): string {
		if (type.startsWith('qa_')) return 'text-orange-400';
		if (type === 'semantic') return 'text-purple-400';
		if (type === 'terminology') return 'text-cyan-400';
		return 'text-zinc-400';
	}

	async function handleExport(format: 'markdown' | 'csv') {
		const content = format === 'markdown' ? exportAsMarkdown() : exportAsCsv();
		const filename = `issues-${new Date().toISOString().slice(0, 10)}.${format === 'markdown' ? 'md' : 'csv'}`;

		// Use clipboard for now (could use Tauri file dialog for save)
		try {
			await navigator.clipboard.writeText(content);
			alert(`Copied ${format.toUpperCase()} to clipboard!\n\nFilename suggestion: ${filename}`);
		} catch {
			// Fallback: show in console
			console.log(`=== ${filename} ===\n${content}`);
			alert('Export copied to console (clipboard failed)');
		}
		showExportMenu = false;
	}
</script>

<div class="w-80 flex flex-col bg-zinc-850 shrink-0 border-l border-zinc-700">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 py-3 bg-zinc-800 border-b border-zinc-700">
		<span class="text-sm font-medium text-zinc-400 uppercase tracking-wide">
			Issues
			{#if totalCount > 0}
				<span class="text-zinc-500">({unresolvedCount}/{totalCount})</span>
			{/if}
		</span>

		{#if totalCount > 0}
			<div class="relative">
				<button
					onclick={() => (showExportMenu = !showExportMenu)}
					class="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-700"
				>
					Export
				</button>
				{#if showExportMenu}
					<div class="absolute right-0 top-full mt-1 bg-zinc-800 border border-zinc-700 rounded shadow-lg z-10">
						<button
							onclick={() => handleExport('markdown')}
							class="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
						>
							Markdown
						</button>
						<button
							onclick={() => handleExport('csv')}
							class="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
						>
							CSV
						</button>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Issues List -->
	<div class="flex-1 overflow-y-auto">
		{#if totalCount === 0}
			<div class="flex items-center justify-center h-full text-zinc-600 text-sm px-4 text-center">
				No issues found yet.<br />
				<span class="text-zinc-700 text-xs mt-1">Run QA or review segments to populate.</span>
			</div>
		{:else}
			{#each [...issuesByType.entries()] as [type, issues]}
				{@const unresolvedInType = issues.filter((i) => !i.resolved).length}
				<div class="border-b border-zinc-700/50">
					<!-- Type Header -->
					<button
						onclick={() => toggleType(type)}
						class="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-zinc-800/50 transition-colors text-left"
					>
						<span
							class="text-zinc-500 transition-transform {expandedTypes.has(type)
								? 'rotate-90'
								: ''}"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="12"
								height="12"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
							>
								<polyline points="9 18 15 12 9 6"></polyline>
							</svg>
						</span>
						<span class="flex-1 text-sm font-medium {getTypeColor(type)}">
							{formatType(type)}
						</span>
						<span class="text-xs text-zinc-500">
							{unresolvedInType}/{issues.length}
						</span>
					</button>

					<!-- Issues in Type -->
					{#if expandedTypes.has(type)}
						<div class="px-3 pb-2 space-y-1.5">
							{#each issues as issue}
								<div
									class="bg-zinc-900/50 rounded p-2 text-xs {issue.resolved
										? 'opacity-50'
										: ''}"
								>
									<div class="flex items-center justify-between mb-1">
										<span class="text-zinc-300 font-medium">
											Seg {issue.segment_id}
										</span>
										<div class="flex items-center gap-1.5">
											<span
												class="px-1.5 py-0.5 rounded text-[10px] {getSeverityColor(
													issue.severity
												)}"
											>
												{issue.severity}
											</span>
											<button
												onclick={() =>
													issue.resolved
														? unresolveIssue(issue.id)
														: resolveIssue(issue.id)}
												class="text-zinc-500 hover:text-zinc-300 transition-colors"
												title={issue.resolved ? 'Mark unresolved' : 'Mark resolved'}
											>
												{#if issue.resolved}
													<svg
														xmlns="http://www.w3.org/2000/svg"
														width="14"
														height="14"
														viewBox="0 0 24 24"
														fill="none"
														stroke="currentColor"
														stroke-width="2"
													>
														<path d="M3 12l6 6L21 6" />
													</svg>
												{:else}
													<svg
														xmlns="http://www.w3.org/2000/svg"
														width="14"
														height="14"
														viewBox="0 0 24 24"
														fill="none"
														stroke="currentColor"
														stroke-width="2"
													>
														<circle cx="12" cy="12" r="10" />
													</svg>
												{/if}
											</button>
										</div>
									</div>

									<p class="text-zinc-400 mb-1 {issue.resolved ? 'line-through' : ''}">
										{issue.message}
									</p>

									{#if issue.source}
										<div class="text-zinc-600 truncate" title={issue.source}>
											<span class="text-zinc-700">S:</span>
											{issue.source.length > 50
												? issue.source.slice(0, 50) + '...'
												: issue.source}
										</div>
									{/if}

									{#if issue.suggested_fix}
										<div class="text-green-400/70 mt-1 text-[10px]">
											→ {issue.suggested_fix}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</div>