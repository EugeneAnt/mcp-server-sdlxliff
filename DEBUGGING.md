# Debugging the SDLXLIFF MCP Server

If the MCP server isn't working correctly in Claude Desktop, follow these debugging steps.

## 1. Check the Server Log

The server writes detailed logs to `/tmp/sdlxliff_mcp_server.log`

View the log:
```bash
tail -f /tmp/sdlxliff_mcp_server.log
```

Or view all recent logs:
```bash
cat /tmp/sdlxliff_mcp_server.log
```

The log shows:
- What directory the server is running from (CWD)
- Which tool calls are being made
- What files are found
- Any errors

## 2. Check Claude Desktop Logs

Claude Desktop also has its own logs that might show MCP errors.

On macOS:
```bash
tail -f ~/Library/Logs/Claude/main.log
```

## 3. Test the Server Directly

Test that the server functions work correctly:

```bash
cd /Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool
.venv/bin/python test_mcp_server.py
```

This will:
- Show the current working directory
- Find all SDLXLIFF files
- Try to read one

## 4. Common Issues

### Issue: "Directory not found" or "File not found"

**Cause**: The MCP server's working directory is different from the folder you added to Claude Cowork.

**Solution**:
1. Check the log to see what CWD the server is using
2. Use the `find_sdlxliff_files` tool WITHOUT specifying a directory - it will search from CWD
3. Use absolute paths from the `find_sdlxliff_files` results

### Issue: MCP tools not showing up

**Cause**: Server configuration or server crash

**Solution**:
1. Check `claude_desktop_config.json` is correct
2. Check Python path is correct
3. Restart Claude Desktop completely
4. Check logs for errors

### Issue: Claude writes scripts instead of using tools

**Cause**: MCP tools are returning errors, so Claude falls back to scripts

**Solution**:
1. Check the server log for errors
2. Make sure files can be found (see Issue #1)
3. Try using `debug_sdlxliff_path` tool to check paths

## 5. Manual Test of MCP Protocol

You can test the MCP server manually:

```bash
cd /Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool
.venv/bin/python server.py
```

Then send JSON-RPC requests via stdin. Example:

```json
{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
```

(Press Ctrl+D to send)

## 6. Recommended Workflow for Claude Cowork

When adding a folder to Claude Cowork, always start with:

```
Find all SDLXLIFF files
```

This will:
1. Show you what the server can see
2. Give you the full paths to use
3. Confirm the server is working

Then use those paths in subsequent commands:

```
Read segments from /full/path/to/file.sdlxliff
```

## 7. Check Server is Running

When you use MCP tools in Claude Desktop, the server should be running as a child process.

Check if it's running:
```bash
ps aux | grep server.py
```

You should see a Python process running `server.py`

## 8. Clear Server Log

If the log gets too large or you want to start fresh:

```bash
rm /tmp/sdlxliff_mcp_server.log
```

The server will create a new one automatically.

## 9. Force Server Reload

If you make changes to the server code:

1. Quit Claude Desktop completely (Cmd+Q)
2. Clear the log: `rm /tmp/sdlxliff_mcp_server.log`
3. Restart Claude Desktop

The server will reload with your changes.

## 10. Contact/Report Issues

If you continue having issues:
1. Collect the server log
2. Collect Claude Desktop log
3. Note what folder you added to Cowork
4. Note what command you gave Claude
5. Note what error occurred