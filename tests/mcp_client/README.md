# --help
```powershell
python mcp_client.py -help
usage: mcp_client.py [-h] [--config CONFIG] [--list] [--list-tools] [--list-tools-detail] [--tool-info SPEC] [--call-tool SPEC] [--arguments JSON]

MCP Client 命令行客户端

options:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        配置文件路径（默认 mcp_servers.json）
  --list, -l            列出所有服务器状态
  --list-tools          列出所有工具
  --list-tools-detail, --detail
                        与 --list-tools 联用，输出每个 tool 的 inputSchema
  --tool-info SPEC      查看单个 tool 的完整 schema。SPEC: server.tool_name 或 tool_name
  --call-tool SPEC      调用指定工具。SPEC 格式同 --tool-info
  --arguments JSON      传给 tool 的参数（JSON 字符串）

使用示例:
  # 默认：连接 mcp_servers.json 中所有 server，输出连接摘要
  python mcp_client.py

  # --list：查看每个 server 的连接状态、传输类型、工具/资源数、错误信息
  python mcp_client.py --list

  # --list-tools：列出所有 server 的全部工具（name + description）
  python mcp_client.py --list-tools

  # --list-tools --detail：额外输出每个 tool 的 inputSchema（参数表 + 原始 JSON）
  python mcp_client.py --list-tools --detail

  # --tool-info server.tool_name：查看某个 server 上某个 tool 的完整 schema
  python mcp_client.py --tool-info searxng.searxng_web_search

  # --tool-info tool_name：跨所有 server 搜索（自动定位到唯一的那个）
  python mcp_client.py --tool-info searxng_web_search

  # --call-tool：调用工具（SPEC 格式同 --tool-info）
  python mcp_client.py --call-tool filesystem.read_text_file
  python mcp_client.py --call-tool filesystem.read_text_file --arguments '{"path": "C:/workspace/README.md"}'
  python mcp_client.py --call-tool searxng.searxng_web_search --arguments '{"query": "MCP protocol", "num_results": 5}'

  # --config：使用非默认配置文件
  python mcp_client.py --config my_servers.json --list-tools

inputSchema 说明:
  MCP 协议规定所有 server 在 tools/list 响应中必须为每个 tool 携带
  inputSchema (标准 JSON Schema) 字段。客户端不依赖 server 端的代码注释
  就能拿到完整的参数定义，本命令就是把这个 schema 印出来。


```

# --list-tools --detail
```powershell
python mcp_client.py --list-tools --detail
已加载 3 个MCP服务器配置
正在初始化MCP客户端...
正在连接服务器: filesystem (type: stdio)
[OK] 服务器 filesystem 连接成功
     工具数量: 14
     资源数量: 0
正在连接服务器: sequentialthinking (type: stdio)
[OK] 服务器 sequentialthinking 连接成功
     工具数量: 1
     资源数量: 0
正在连接服务器: searxng (type: stdio)
[OK] 服务器 searxng 连接成功
     工具数量: 4
     资源数量: 2

连接完成: 3/3 个服务器成功

服务器 'filesystem' 的工具:

  ╭─ read_file
  │  Description: Read the complete contents of a file as text. DEPRECATED: Use read_text_file instead.
  │
  │      Parameters (3):
  │        - path  string  [required]
  │        - tail  number  [optional]
  │                If provided, returns only the last N lines of the file
  │        - head  number  [optional]
  │                If provided, returns only the first N lines of the file
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "tail": {
  │          "description": "If provided, returns only the last N lines of the file",
  │          "type": "number"
  │        },
  │        "head": {
  │          "description": "If provided, returns only the first N lines of the file",
  │          "type": "number"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ read_text_file
  │  Description: Read the complete contents of a file from the file system as text. Handles various text encodings and provides detailed error messages if the file cannot be read. Use this tool when you need to examine the contents of a single file. Use the 'head' parameter to read only the first N lines of a file, or the 'tail' parameter to read only the last N lines of a file. Operates on the file as text regardless of extension. Only works within allowed directories.
  │
  │      Parameters (3):
  │        - path  string  [required]
  │        - tail  number  [optional]
  │                If provided, returns only the last N lines of the file
  │        - head  number  [optional]
  │                If provided, returns only the first N lines of the file
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "tail": {
  │          "description": "If provided, returns only the last N lines of the file",
  │          "type": "number"
  │        },
  │        "head": {
  │          "description": "If provided, returns only the first N lines of the file",
  │          "type": "number"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ read_media_file
  │  Description: Read a file and return it as a base64-encoded content block with its MIME type. Image and audio files are returned as image/audio content; any other file type is returned as an embedded resource. Only works within allowed directories.
  │
  │      Parameters (1):
  │        - path  string  [required]
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ read_multiple_files
  │  Description: Read the contents of multiple files simultaneously. This is more efficient than reading files one by one when you need to analyze or compare multiple files. Each file's content is returned with its path as a reference. Failed reads for individual files won't stop the entire operation. Only works within allowed directories.
  │
  │      Parameters (1):
  │        - paths  array<string>  [required]
  │                 Array of file paths to read. Each path must be a string pointing to a valid file within allowed directories.
  │      Required: paths
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "paths": {
  │          "minItems": 1,
  │          "type": "array",
  │          "items": {
  │            "type": "string"
  │          },
  │          "description": "Array of file paths to read. Each path must be a string pointing to a valid file within allowed directories."
  │        }
  │      },
  │      "required": [
  │        "paths"
  │      ]
  │    }
  ╰─

  ╭─ write_file
  │  Description: Create a new file or completely overwrite an existing file with new content. Use with caution as it will overwrite existing files without warning. Handles text content with proper encoding. Only works within allowed directories.
  │
  │      Parameters (2):
  │        - path     string  [required]
  │        - content  string  [required]
  │      Required: content, path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "content": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "path",
  │        "content"
  │      ]
  │    }
  ╰─

  ╭─ edit_file
  │  Description: Make line-based edits to a text file. Each edit replaces exact line sequences with new content. Returns a git-style diff showing the changes made. Only works within allowed directories.
  │
  │      Parameters (3):
  │        - path    string  [required]
  │        - edits   array<object>  [required]
  │        - dryRun  boolean  [optional]  default: False
  │                  Preview changes using git-style diff format
  │      Required: edits, path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "edits": {
  │          "type": "array",
  │          "items": {
  │            "type": "object",
  │            "properties": {
  │              "oldText": {
  │                "type": "string",
  │                "description": "Text to search for - must match exactly"
  │              },
  │              "newText": {
  │                "type": "string",
  │                "description": "Text to replace with"
  │              }
  │            },
  │            "required": [
  │              "oldText",
  │              "newText"
  │            ]
  │          }
  │        },
  │        "dryRun": {
  │          "default": false,
  │          "description": "Preview changes using git-style diff format",
  │          "type": "boolean"
  │        }
  │      },
  │      "required": [
  │        "path",
  │        "edits"
  │      ]
  │    }
  ╰─

  ╭─ create_directory
  │  Description: Create a new directory or ensure a directory exists. Can create multiple nested directories in one operation. If the directory already exists, this operation will succeed silently. Perfect for setting up directory structures for projects or ensuring required paths exist. Only works within allowed directories.
  │
  │      Parameters (1):
  │        - path  string  [required]
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ list_directory
  │  Description: Get a detailed listing of all files and directories in a specified path. Results clearly distinguish between files and directories with [FILE] and [DIR] prefixes. This tool is essential for understanding directory structure and finding specific files within a directory. Only works within allowed directories.
  │
  │      Parameters (1):
  │        - path  string  [required]
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ list_directory_with_sizes
  │  Description: Get a detailed listing of all files and directories in a specified path, including sizes. Results clearly distinguish between files and directories with [FILE] and [DIR] prefixes. This tool is useful for understanding directory structure and finding specific files within a directory. Only works within allowed directories.
  │
  │      Parameters (2):
  │        - path    string  [required]
  │        - sortBy  string  [optional]  enum: 'name', 'size'  default: 'name'
  │                  Sort entries by name or size
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "sortBy": {
  │          "default": "name",
  │          "description": "Sort entries by name or size",
  │          "type": "string",
  │          "enum": [
  │            "name",
  │            "size"
  │          ]
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ directory_tree
  │  Description: Get a recursive tree view of files and directories as a JSON structure. Each entry includes 'name', 'type' (file/directory), and 'children' for directories. Files have no children array, while directories always have a children array (which may be empty). The output is formatted with 2-space indentation for readability. Only works within allowed directories.
  │
  │      Parameters (2):
  │        - path             string  [required]
  │        - excludePatterns  array<string>  [optional]  default: []
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "excludePatterns": {
  │          "default": [],
  │          "type": "array",
  │          "items": {
  │            "type": "string"
  │          }
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ move_file
  │  Description: Move or rename files and directories. Can move files between directories and rename them in a single operation. If the destination exists, the operation will fail. Works across different directories and can be used for simple renaming within the same directory. Both source and destination must be within allowed directories.
  │
  │      Parameters (2):
  │        - source       string  [required]
  │        - destination  string  [required]
  │      Required: destination, source
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "source": {
  │          "type": "string"
  │        },
  │        "destination": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "source",
  │        "destination"
  │      ]
  │    }
  ╰─

  ╭─ search_files
  │  Description: Recursively search for files and directories matching a pattern. The patterns should be glob-style patterns that match paths relative to the working directory. Use pattern like '*.ext' to match files in current directory, and '**/*.ext' to match files in all subdirectories. Returns full paths to all matching items. Great for finding files when you don't know their exact location. Only searches within allowed directories.
  │
  │      Parameters (3):
  │        - path             string  [required]
  │        - pattern          string  [required]
  │        - excludePatterns  array<string>  [optional]  default: []
  │      Required: path, pattern
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        },
  │        "pattern": {
  │          "type": "string"
  │        },
  │        "excludePatterns": {
  │          "default": [],
  │          "type": "array",
  │          "items": {
  │            "type": "string"
  │          }
  │        }
  │      },
  │      "required": [
  │        "path",
  │        "pattern"
  │      ]
  │    }
  ╰─

  ╭─ get_file_info
  │  Description: Retrieve detailed metadata about a file or directory. Returns comprehensive information including size, creation time, last modified time, permissions, and type. This tool is perfect for understanding file characteristics without reading the actual content. Only works within allowed directories.
  │
  │      Parameters (1):
  │        - path  string  [required]
  │      Required: path
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "path": {
  │          "type": "string"
  │        }
  │      },
  │      "required": [
  │        "path"
  │      ]
  │    }
  ╰─

  ╭─ list_allowed_directories
  │  Description: Returns the list of directories that this server is allowed to access. Subdirectories within these allowed directories are also accessible. Use this to understand which directories and their nested paths are available before trying to access files.
  │
  │      {
  │          "$schema": "http://json-schema.org/draft-07/schema#",
  │          "type": "object",
  │          "properties": {}
  │      }
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {}
  │    }
  ╰─

服务器 'sequentialthinking' 的工具:

  ╭─ sequentialthinking
  │  Description: A detailed tool for dynamic and reflective problem-solving through thoughts.
This tool helps analyze problems through a flexible thinking process that can adapt and evolve.
Each thought can build on, question, or revise previous insights as understanding deepens.

When to use this tool:
- Breaking down complex problems into steps
- Planning and design with room for revision
- Analysis that might need course correction
- Problems where the full scope might not be clear initially
- Problems that require a multi-step solution
- Tasks that need to maintain context over multiple steps
- Situations where irrelevant information needs to be filtered out

Key features:
- You can adjust total_thoughts up or down as you progress
- You can question or revise previous thoughts
- You can add more thoughts even after reaching what seemed like the end
- You can express uncertainty and explore alternative approaches
- Not every thought needs to build linearly - you can branch or backtrack
- Generates a solution hypothesis
- Verifies the hypothesis based on the Chain of Thought steps
- Repeats the process until satisfied
- Provides a correct answer

Parameters explained:
- thought: Your current thinking step, which can include:
  * Regular analytical steps
  * Revisions of previous thoughts
  * Questions about previous decisions
  * Realizations about needing more analysis
  * Changes in approach
  * Hypothesis generation
  * Hypothesis verification
- nextThoughtNeeded: True if you need more thinking, even if at what seemed like the end
- thoughtNumber: Current number in sequence (can go beyond initial total if needed)
- totalThoughts: Current estimate of thoughts needed (can be adjusted up/down)
- isRevision: A boolean indicating if this thought revises previous thinking
- revisesThought: If is_revision is true, which thought number is being reconsidered
- branchFromThought: If branching, which thought number is the branching point
- branchId: Identifier for the current branch (if any)
- needsMoreThoughts: If reaching end but realizing more thoughts needed

You should:
1. Start with an initial estimate of needed thoughts, but be ready to adjust
2. Feel free to question or revise previous thoughts
3. Don't hesitate to add more thoughts if needed, even at the "end"
4. Express uncertainty when present
5. Mark thoughts that revise previous thinking or branch into new paths
6. Ignore information that is irrelevant to the current step
7. Generate a solution hypothesis when appropriate
8. Verify the hypothesis based on the Chain of Thought steps
9. Repeat the process until satisfied with the solution
10. Provide a single, ideally correct answer as the final output
11. Only set nextThoughtNeeded to false when truly done and a satisfactory answer is reached
  │
  │      Parameters (9):
  │        - thought            string  [required]
  │                             Your current thinking step
  │        - nextThoughtNeeded  boolean  [optional]
  │                             Whether another thought step is needed
  │        - thoughtNumber      integer  [required]
  │                             Current thought number (numeric value, e.g., 1, 2, 3)
  │        - totalThoughts      integer  [required]
  │                             Estimated total thoughts needed (numeric value, e.g., 5, 10)
  │        - isRevision         boolean  [optional]
  │                             Whether this revises previous thinking
  │        - revisesThought     integer  [optional]
  │                             Which thought is being reconsidered
  │        - branchFromThought  integer  [optional]
  │                             Branching point thought number
  │        - branchId           string  [optional]
  │                             Branch identifier
  │        - needsMoreThoughts  boolean  [optional]
  │                             If more thoughts are needed
  │      Required: thought, thoughtNumber, totalThoughts
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "$schema": "http://json-schema.org/draft-07/schema#",
  │      "type": "object",
  │      "properties": {
  │        "thought": {
  │          "type": "string",
  │          "description": "Your current thinking step"
  │        },
  │        "nextThoughtNeeded": {
  │          "description": "Whether another thought step is needed",
  │          "type": "boolean"
  │        },
  │        "thoughtNumber": {
  │          "type": "integer",
  │          "minimum": 1,
  │          "maximum": 9007199254740991,
  │          "description": "Current thought number (numeric value, e.g., 1, 2, 3)"
  │        },
  │        "totalThoughts": {
  │          "type": "integer",
  │          "minimum": 1,
  │          "maximum": 9007199254740991,
  │          "description": "Estimated total thoughts needed (numeric value, e.g., 5, 10)"
  │        },
  │        "isRevision": {
  │          "description": "Whether this revises previous thinking",
  │          "type": "boolean"
  │        },
  │        "revisesThought": {
  │          "description": "Which thought is being reconsidered",
  │          "type": "integer",
  │          "minimum": 1,
  │          "maximum": 9007199254740991
  │        },
  │        "branchFromThought": {
  │          "description": "Branching point thought number",
  │          "type": "integer",
  │          "minimum": 1,
  │          "maximum": 9007199254740991
  │        },
  │        "branchId": {
  │          "description": "Branch identifier",
  │          "type": "string"
  │        },
  │        "needsMoreThoughts": {
  │          "description": "If more thoughts are needed",
  │          "type": "boolean"
  │        }
  │      },
  │      "required": [
  │        "thought",
  │        "thoughtNumber",
  │        "totalThoughts"
  │      ]
  │    }
  ╰─

服务器 'searxng' 的工具:

  ╭─ searxng_web_search
  │  Description: Searches the web using SearXNG and returns a list of results, each with a title, URL, and content snippet. CRITICAL: The required parameter name is exactly `query` (not `prompt`, `q`, or any other name). Calls an external SearXNG instance; availability depends on the `SEARXNG_URL` configuration. Use `pageno` to paginate results; combine `time_range` and `language` to narrow scope. To read the full text of a result URL, follow up with `web_url_read`.
  │
  │      Parameters (10):
  │        - query            string  [required]
  │                           The search query string. This is the required parameter name — use exactly `query`, not `prompt` or `q`.
  │        - pageno           number  [optional]  default: 1
  │                           Search page number (starts at 1)
  │        - time_range       string  [optional]  enum: 'day', 'week', 'month', 'year'
  │                           Time range of search (day, week, month, year)
  │        - language         string  [optional]  default: 'all'
  │                           Language code for search results (e.g., 'en', 'fr', 'de'). Default is instance-dependent.
  │        - safesearch       string  [optional]  enum: '0', '1', '2'
  │                           Safe search filter level (0: None, 1: Moderate, 2: Strict)
  │        - min_score        number  [optional]
  │                           Minimum relevance score threshold from 0.0 to 1.0. Results below this score are filtered out.
  │        - num_results      number  [optional]
  │                           Maximum number of results to return (1-20). Operator cap SEARXNG_MAX_RESULTS applies as a ceiling.
  │        - categories       string  [optional]
  │                           Comma-separated SearXNG categories. Live /config capabilities are aggregated across reachable instances; prefer searxng_instance_info categories.common for consistent multi-instance results. Values in categories.available are best-effort and may only be honored by some instances. Known values are normalized case-insensitively; unknown values are forwarded trimmed so SearXNG can ignore or honor them. If /config is unavailable, values are forwarded as-is with a warning. If omitted, each instance uses its server-side default.
  │        - engines          string  [optional]
  │                           Comma-separated SearXNG engine names to query (e.g. 'google,bing,ddg'). Live /config capabilities are aggregated across reachable instances; prefer searxng_instance_info engines.common.enabled for consistent multi-instance results. Values in engines.available.enabled are best-effort and may only be honored by some instances. Known values are normalized case-insensitively; unknown values are forwarded trimmed so SearXNG can ignore or honor them. If /config is unavailable, values are forwarded as-is with a warning. If omitted, each instance uses its server-side default.
  │        - response_format  string  [optional]  enum: 'text', 'json'  default: 'text'
  │                           Response format: formatted text for agents or raw JSON for programmatic clients. Default: text.
  │      Required: query
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "type": "object",
  │      "properties": {
  │        "query": {
  │          "type": "string",
  │          "description": "The search query string. This is the required parameter name — use exactly `query`, not `prompt` or `q`."
  │        },
  │        "pageno": {
  │          "type": "number",
  │          "description": "Search page number (starts at 1)",
  │          "default": 1
  │        },
  │        "time_range": {
  │          "type": "string",
  │          "description": "Time range of search (day, week, month, year)",
  │          "enum": [
  │            "day",
  │            "week",
  │            "month",
  │            "year"
  │          ]
  │        },
  │        "language": {
  │          "type": "string",
  │          "description": "Language code for search results (e.g., 'en', 'fr', 'de'). Default is instance-dependent.",
  │          "default": "all"
  │        },
  │        "safesearch": {
  │          "type": "string",
  │          "description": "Safe search filter level (0: None, 1: Moderate, 2: Strict)",
  │          "enum": [
  │            "0",
  │            "1",
  │            "2"
  │          ]
  │        },
  │        "min_score": {
  │          "type": "number",
  │          "description": "Minimum relevance score threshold from 0.0 to 1.0. Results below this score are filtered out.",
  │          "minimum": 0,
  │          "maximum": 1
  │        },
  │        "num_results": {
  │          "type": "number",
  │          "description": "Maximum number of results to return (1-20). Operator cap SEARXNG_MAX_RESULTS applies as a ceiling.",
  │          "minimum": 1,
  │          "maximum": 20
  │        },
  │        "categories": {
  │          "type": "string",
  │          "description": "Comma-separated SearXNG categories. Live /config capabilities are aggregated across reachable instances; prefer searxng_instance_info categories.common for consistent multi-instance results. Values in categories.available are best-effort and may only be honored by some instances. Known values are normalized case-insensitively; unknown values are forwarded trimmed so SearXNG can ignore or honor them. If /config is unavailable, values are forwarded as-is with a warning. If omitted, each instance uses its server-side default."
  │        },
  │        "engines": {
  │          "type": "string",
  │          "description": "Comma-separated SearXNG engine names to query (e.g. 'google,bing,ddg'). Live /config capabilities are aggregated across reachable instances; prefer searxng_instance_info engines.common.enabled for consistent multi-instance results. Values in engines.available.enabled are best-effort and may only be honored by some instances. Known values are normalized case-insensitively; unknown values are forwarded trimmed so SearXNG can ignore or honor them. If /config is unavailable, values are forwarded as-is with a warning. If omitted, each instance uses its server-side default."
  │        },
  │        "response_format": {
  │          "type": "string",
  │          "description": "Response format: formatted text for agents or raw JSON for programmatic clients. Default: text.",
  │          "enum": [
  │            "text",
  │            "json"
  │          ],
  │          "default": "text"
  │        }
  │      },
  │      "required": [
  │        "query"
  │      ]
  │    }
  ╰─

  ╭─ searxng_search_suggestions
  │  Description: Returns autocomplete suggestions from the configured SearXNG instance. Use this to refine vague or partial queries before searching.
  │
  │      Parameters (2):
  │        - query     string  [required]
  │                    Partial or complete query to autocomplete.
  │        - language  string  [optional]  default: 'all'
  │                    Language code for suggestions (e.g., 'en', 'fr', 'de') or 'all'. Default: all.
  │      Required: query
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "type": "object",
  │      "properties": {
  │        "query": {
  │          "type": "string",
  │          "description": "Partial or complete query to autocomplete."
  │        },
  │        "language": {
  │          "type": "string",
  │          "description": "Language code for suggestions (e.g., 'en', 'fr', 'de') or 'all'. Default: all.",
  │          "default": "all"
  │        }
  │      },
  │      "required": [
  │        "query"
  │      ]
  │    }
  ╰─

  ╭─ searxng_instance_info
  │  Description: Discovers capabilities from all reachable configured SearXNG instances via /config, including categories.common/available, engines.common/available, defaults, locales, and plugins.
  │
  │      Parameters (4):
  │        - includeEngines   boolean  [optional]  default: False
  │                           Include enabled engine names in the response.
  │        - includeDisabled  boolean  [optional]  default: False
  │                           Include disabled engine names when includeEngines is true.
  │        - category         string  [optional]
  │                           Filter categories and engines to a single category name.
  │        - refresh          boolean  [optional]  default: False
  │                           Bypass the process cache and fetch fresh /config data.
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "type": "object",
  │      "properties": {
  │        "includeEngines": {
  │          "type": "boolean",
  │          "description": "Include enabled engine names in the response.",
  │          "default": false
  │        },
  │        "includeDisabled": {
  │          "type": "boolean",
  │          "description": "Include disabled engine names when includeEngines is true.",
  │          "default": false
  │        },
  │        "category": {
  │          "type": "string",
  │          "description": "Filter categories and engines to a single category name."
  │        },
  │        "refresh": {
  │          "type": "boolean",
  │          "description": "Bypass the process cache and fetch fresh /config data.",
  │          "default": false
  │        }
  │      },
  │      "required": []
  │    }
  ╰─

  ╭─ web_url_read
  │  Description: Fetches a URL and returns readable content as markdown. Content-type aware: HTML is converted to markdown; JSON is pretty-printed; plain text, YAML, TOML, and XML are returned as fenced readable text. Binary, media, archive, PDF, and octet-stream downloads are intentionally rejected instead of being returned as raw bytes. Three modes: (1) Full content — omit filtering params; use `startChar`/`maxLength` to paginate large pages. (2) Section extraction — set `section` to return content under a specific heading. (3) Headings only — set `readHeadings: true` to list all headings (mutually exclusive with other filtering params). Returns an error string if the URL is unreachable or content cannot be extracted. Use after `searxng_web_search` to read the full content of individual result URLs.
  │
  │      Parameters (6):
  │        - url             string  [required]
  │                          URL
  │        - startChar       number  [optional]
  │                          Starting character position for content extraction (default: 0)
  │        - maxLength       number  [optional]
  │                          Maximum number of characters to return
  │        - section         string  [optional]
  │                          Extract content under a specific heading (searches for heading text)
  │        - paragraphRange  string  [optional]
  │                          Return specific paragraph ranges (e.g., '1-5', '3', '10-')
  │        - readHeadings    boolean  [optional]
  │                          Return only a list of headings instead of full content
  │      Required: url
  │
  │  Raw inputSchema (JSON Schema):
  │    {
  │      "type": "object",
  │      "properties": {
  │        "url": {
  │          "type": "string",
  │          "description": "URL"
  │        },
  │        "startChar": {
  │          "type": "number",
  │          "description": "Starting character position for content extraction (default: 0)",
  │          "minimum": 0
  │        },
  │        "maxLength": {
  │          "type": "number",
  │          "description": "Maximum number of characters to return",
  │          "minimum": 1
  │        },
  │        "section": {
  │          "type": "string",
  │          "description": "Extract content under a specific heading (searches for heading text)"
  │        },
  │        "paragraphRange": {
  │          "type": "string",
  │          "description": "Return specific paragraph ranges (e.g., '1-5', '3', '10-')"
  │        },
  │        "readHeadings": {
  │          "type": "boolean",
  │          "description": "Return only a list of headings instead of full content"
  │        }
  │      },
  │      "required": [
  │        "url"
  │      ]
  │    }
  ╰─

```

## 错误处理示例

tool 不存在时，提示同 server 上的其他工具名:

```powershell
python mcp_client.py --tool-info filesystem.no_such_tool
```
```
错误: 在 'filesystem' 中找不到工具 'no_such_tool'
提示: 'filesystem' 上的工具: read_file, read_text_file, read_media_file, ...
```

tool 名在多个 server 上存在时:

```powershell
python mcp_client.py --tool-info some_common_tool
```

```
工具 'some_common_tool' 在多个服务器上存在，输出全部匹配:
  - server_a.some_common_tool
  - server_b.some_common_tool
请用 --tool-info <server_name>.<tool_name> 指定具体服务器
```

# 关于 inputSchema 的来源（FAQ）

**Q: 工具的传参信息是从哪里来的？是从 server 的代码注释里读的吗？**

**A: 不是。** MCP 协议规定所有 server 在响应 `tools/list` 时必须为每个 tool 携带 `inputSchema` 字段（标准 JSON Schema 格式）。这是协议层硬性要求，**与 server 用什么语言实现无关**。

不同语言 SDK 只是在「**如何让 server 端开发者声明这个 schema**」上写法不同：

| 语言/SDK | 声明方式 | 是否自动生成 inputSchema |
|---|---|---|
| **Python (FastMCP)** | `@server.tool()` + 类型注解 + docstring | ✅ SDK 用 `inspect` + `pydantic` 从函数签名自动生成 |
| **TypeScript** | `server.tool("name", "desc", { name: z.string() })` 用 **Zod** | ✅ SDK 从 Zod schema 转 |
| **Go** | `mcp.WithToolDescription(...)` + `mcp.WithObjectSchema(...)` | ❌ 手动写 JSON Schema |
| **Rust** | `#[tool(...)]` + `schemars::JsonSchema` derive | ✅ 从 Rust 类型 derive |
| **C# / .NET** | `[McpServerTool]` + 参数的 `[Description]` attribute | ✅ 从类型 + attribute 生成 |

所以你只要用 `--tool-info` / `--list-tools --detail` 拿到的 schema，就是这个 tool **真实可用的传参定义**，不需要去看 server 源码、也不需要去翻注释。

