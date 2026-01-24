<script lang="ts">
	import { selectedModel } from '$lib/stores/models';
</script>

<select
	bind:value={$selectedModel}
	title="Select AI model"
	class="text-sm px-2 py-1.5 rounded bg-zinc-700 text-zinc-200 border border-zinc-600 focus:border-blue-500 focus:outline-none cursor-pointer"
>
	<option value="sonnet">Sonnet 4.5</option>
	<option value="haiku">Haiku 4.5</option>
</select>
