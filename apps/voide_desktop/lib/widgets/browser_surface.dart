import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../services/ipc_client.dart';

class BrowserSurface extends StatefulWidget {
  final IPCClient ipc;

  const BrowserSurface({super.key, required this.ipc});

  @override
  State<BrowserSurface> createState() => _BrowserSurfaceState();
}

class _BrowserSurfaceState extends State<BrowserSurface> {
  final TextEditingController _urlController = TextEditingController(text: 'http://localhost:3000');
  
  // LLM Gateway Controllers
  final TextEditingController _apiKeyController = TextEditingController();
  final TextEditingController _baseUrlController = TextEditingController(text: 'https://api.openai.com/v1');
  final TextEditingController _modelController = TextEditingController(text: 'gpt-4o');
  String _activeProvider = 'openai';
  bool _obscureApiKey = true;
  Map<String, dynamic> _llmConfig = {};
  String _llmStatusMessage = 'Loading LLM Gateway status...';

  bool _isLoading = false;
  Uint8List? _screenshotBytes;

  Map<String, dynamic> _browserStatus = {
    'connected': false,
    'port': 9222,
    'profile_dir': '~/.config/voide/chromium_profile',
    'active_url': 'about:blank',
    'active_title': 'Browser Viewport',
    'tab_count': 0,
    'mapping_version': 1,
    'cached_elements_count': 0,
  };

  Map<String, dynamic> _inspectedTargets = {};
  List<dynamic> _discoveredElements = [];
  String _statusMessage = 'Browser viewport engine ready. Enter URL and click GO.';
  int _activeViewIndex = 0; // 0: LLM Gateway, 1: Viewport & Targets, 2: DOM Catalog, 3: Architecture

  @override
  void initState() {
    super.initState();
    _fetchLlmConfig();
    _refreshBrowserStatus();
  }

  Future<void> _fetchLlmConfig() async {
    try {
      final res = await widget.ipc.send('llm_get_config');
      if (res is Map) {
        setState(() {
          _llmConfig = Map<String, dynamic>.from(res);
          _baseUrlController.text = _llmConfig['base_url'] ?? 'https://api.openai.com/v1';
          _modelController.text = _llmConfig['model'] ?? 'gpt-4o';
          _activeProvider = _llmConfig['provider'] ?? 'openai';
          _llmStatusMessage = _llmConfig['api_key_configured'] == true
              ? 'LLM API Gateway active with ${_llmConfig['model']} (${_llmConfig['provider']})'
              : 'API Key not configured. Enter a key or use local Ollama.';
        });
      }
    } catch (e) {
      setState(() => _llmStatusMessage = 'Failed to load LLM config: $e');
    }
  }

  Future<void> _saveLlmConfig() async {
    setState(() => _isLoading = true);
    try {
      final res = await widget.ipc.send('llm_set_config', {
        if (_apiKeyController.text.trim().isNotEmpty) 'api_key': _apiKeyController.text.trim(),
        'base_url': _baseUrlController.text.trim(),
        'model': _modelController.text.trim(),
        'provider': _activeProvider,
      });
      if (res is Map) {
        setState(() {
          _llmConfig = Map<String, dynamic>.from(res);
          _llmStatusMessage = 'LLM Configuration successfully updated & active!';
          _apiKeyController.clear();
        });
      }
    } catch (e) {
      setState(() => _llmStatusMessage = 'Error updating LLM config: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _applyPreset(String provider, String baseUrl, String model) {
    setState(() {
      _activeProvider = provider;
      _baseUrlController.text = baseUrl;
      _modelController.text = model;
    });
  }

  Future<void> _refreshBrowserStatus() async {
    setState(() => _isLoading = true);
    try {
      final res = await widget.ipc.send('browser_status');
      if (res is Map) {
        setState(() {
          _browserStatus = Map<String, dynamic>.from(res);
          if (_browserStatus['active_url'] != null && _browserStatus['active_url'] != 'about:blank') {
            _urlController.text = _browserStatus['active_url'];
          }
        });
      }
      final targetsRes = await widget.ipc.send('browser_inspect');
      if (targetsRes is Map) {
        setState(() {
          _inspectedTargets = Map<String, dynamic>.from(targetsRes['targets'] ?? targetsRes);
        });
      }
      if (_browserStatus['connected'] == true) {
        await _captureScreenshot();
      }
    } catch (e) {
      setState(() => _statusMessage = 'Status check: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _captureScreenshot() async {
    setState(() => _isLoading = true);
    try {
      final res = await widget.ipc.send('browser_screenshot');
      if (res is Map && res['screenshot_base64'] != null) {
        final b64 = res['screenshot_base64'] as String;
        final bytes = base64Decode(b64);
        setState(() {
          _screenshotBytes = bytes;
          _statusMessage = 'Live viewport screenshot captured (${(bytes.length / 1024).toStringAsFixed(1)} KB)';
        });
      } else {
        setState(() => _statusMessage = 'Screenshot unavailable (launch browser viewport first)');
      }
    } catch (e) {
      setState(() => _statusMessage = 'Screenshot error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _discoverLiveElements() async {
    setState(() => _isLoading = true);
    try {
      final res = await widget.ipc.send('browser_discover');
      if (res is Map && res['elements'] != null) {
        setState(() {
          _discoveredElements = res['elements'] as List<dynamic>;
          _statusMessage = 'Discovered ${_discoveredElements.length} live DOM elements via DOM Intelligence script';
        });
      }
      await _refreshBrowserStatus();
    } catch (e) {
      setState(() => _statusMessage = 'Discovery error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _revealElement(String selector, String title) async {
    try {
      await widget.ipc.send('browser_reveal', {'selector': selector, 'title': title});
      setState(() => _statusMessage = 'Pulsing reveal overlay dispatched for "$title" ($selector)');
      await _captureScreenshot();
    } catch (e) {
      setState(() => _statusMessage = 'Reveal error: $e');
    }
  }

  Future<void> _dispatchBrowserAction(String selector, String actionType, [String? param]) async {
    setState(() => _isLoading = true);
    try {
      final res = await widget.ipc.send('browser_action', {
        'selector': selector,
        'action_type': actionType,
        'param': param,
      });
      setState(() => _statusMessage = 'Action "$actionType" executed on $selector: $res');
      await Future.delayed(const Duration(milliseconds: 300));
      await _captureScreenshot();
    } catch (e) {
      setState(() => _statusMessage = 'Action error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _launchChromium([String? url]) async {
    setState(() {
      _isLoading = true;
      _statusMessage = 'Launching browser viewport...';
    });
    try {
      final targetUrl = url ?? _urlController.text.trim();
      final res = await widget.ipc.send('browser_launch', {
        'url': targetUrl,
        'show_window': true,
      });
      if (res is Map && res['status'] != null) {
        setState(() {
          _browserStatus = Map<String, dynamic>.from(res['status']);
          _statusMessage = 'Viewport launched on $targetUrl';
        });
      }
      await Future.delayed(const Duration(milliseconds: 1000));
      await _refreshBrowserStatus();
    } catch (e) {
      setState(() => _statusMessage = 'Launch error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _navigate() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) return;
    setState(() => _isLoading = true);
    try {
      await widget.ipc.send('browser_navigate', {'url': url});
      setState(() => _statusMessage = 'Navigated to $url');
      await _refreshBrowserStatus();
      await Future.delayed(const Duration(milliseconds: 600));
      await _captureScreenshot();
    } catch (e) {
      setState(() => _statusMessage = 'Navigation error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF000000),
      child: Column(
        children: [
          if (_isLoading)
            const LinearProgressIndicator(
              minHeight: 2,
              color: Colors.white,
              backgroundColor: Color(0xFF1A1A1A),
            ),
          // Browser Navigation Bar
          Container(
            height: 40,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: const BoxDecoration(
              color: Color(0xFF0A0A0A),
              border: Border(bottom: BorderSide(color: Color(0xFF1E1E1E))),
            ),
            child: Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.refresh, size: 14, color: Color(0xFF888888)),
                  onPressed: _refreshBrowserStatus,
                  tooltip: 'Reload & Sync',
                  splashRadius: 14,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 26, minHeight: 26),
                ),
                const SizedBox(width: 8),
                // URL Bar
                Expanded(
                  child: Container(
                    height: 26,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF111111),
                      borderRadius: BorderRadius.circular(3),
                      border: Border.all(color: const Color(0xFF262626)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.language, size: 12, color: Colors.white),
                        const SizedBox(width: 6),
                        Expanded(
                          child: TextField(
                            controller: _urlController,
                            style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace'),
                            decoration: const InputDecoration(
                              hintText: 'Enter local URL or web address...',
                              hintStyle: TextStyle(color: Color(0xFF555555), fontSize: 11),
                              border: InputBorder.none,
                              isDense: true,
                              contentPadding: EdgeInsets.zero,
                            ),
                            onSubmitted: (_) => _navigate(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _navigate,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    minimumSize: Size.zero,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
                  ),
                  child: const Text('GO', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
          // Action Buttons Bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            color: const Color(0xFF080808),
            child: Row(
              children: [
                ElevatedButton.icon(
                  onPressed: () => _launchChromium(),
                  icon: const Icon(Icons.open_in_new, size: 12),
                  label: const Text('Launch Viewport Window', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    minimumSize: Size.zero,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
                  ),
                ),
                const SizedBox(width: 6),
                OutlinedButton.icon(
                  onPressed: _captureScreenshot,
                  icon: const Icon(Icons.camera_alt_outlined, size: 12),
                  label: const Text('Capture Viewport', style: TextStyle(fontSize: 10)),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Color(0xFF444444)),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    minimumSize: Size.zero,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
                  ),
                ),
                const SizedBox(width: 6),
                OutlinedButton.icon(
                  onPressed: _discoverLiveElements,
                  icon: const Icon(Icons.search, size: 12),
                  label: const Text('Discover DOM', style: TextStyle(fontSize: 10)),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Color(0xFF444444)),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    minimumSize: Size.zero,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: _llmConfig['api_key_configured'] == true ? const Color(0xFF14532D) : const Color(0xFF78350F),
                    borderRadius: BorderRadius.circular(3),
                  ),
                  child: Text(
                    _llmConfig['api_key_configured'] == true ? 'AI: READY' : 'AI: KEY PENDING',
                    style: const TextStyle(color: Colors.white, fontSize: 8.5, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ),
          // Sub-navigation View Switcher
          Container(
            height: 32,
            decoration: const BoxDecoration(
              color: Color(0xFF0F0F0F),
              border: Border(bottom: BorderSide(color: Color(0xFF1E1E1E))),
            ),
            child: Row(
              children: [
                _viewTabButton(0, 'AI GATEWAY & API KEY'),
                _viewTabButton(1, 'VIEWPORT & TARGETS'),
                _viewTabButton(2, 'DOM CATALOG'),
                _viewTabButton(3, 'ARCHITECTURE & TELEMETRY'),
              ],
            ),
          ),
          Expanded(child: _buildActiveView()),
        ],
      ),
    );
  }

  Widget _viewTabButton(int index, String label) {
    final active = _activeViewIndex == index;
    return InkWell(
      onTap: () => setState(() => _activeViewIndex = index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: active ? const Color(0xFF1A1A1A) : Colors.transparent,
          border: Border(
            bottom: BorderSide(color: active ? Colors.white : Colors.transparent, width: 2),
            right: const BorderSide(color: Color(0xFF1A1A1A)),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? Colors.white : const Color(0xFF777777),
            fontSize: 9.5,
            fontWeight: active ? FontWeight.bold : FontWeight.w500,
            letterSpacing: 0.8,
          ),
        ),
      ),
    );
  }

  Widget _buildActiveView() {
    switch (_activeViewIndex) {
      case 0:
        return _buildLlmGatewayView();
      case 1:
        return _buildViewportAndTargetsView();
      case 2:
        return _buildDomCatalogView();
      case 3:
      default:
        return _buildResolverTelemetryView();
    }
  }

  Widget _buildLlmGatewayView() {
    final hasKey = _llmConfig['api_key_configured'] == true;
    final maskedKey = _llmConfig['api_key_masked'] ?? 'Not set';

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Status Card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF0C0C0C),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    hasKey ? Icons.check_circle_outline : Icons.warning_amber_rounded,
                    size: 16,
                    color: hasKey ? const Color(0xFF22C55E) : const Color(0xFFF59E0B),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'AI REASONING GATEWAY STATUS',
                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 0.8),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: hasKey ? const Color(0xFF166534) : const Color(0xFF991B1B),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      hasKey ? 'ACTIVE' : 'KEY MISSING',
                      style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                _llmStatusMessage,
                style: const TextStyle(color: Color(0xFFB0B0B0), fontSize: 11),
              ),
              const SizedBox(height: 12),
              const Divider(color: Color(0xFF1E1E1E)),
              const SizedBox(height: 8),
              Row(
                children: [
                  _statusBadge('Provider', _llmConfig['provider'] ?? 'openai'),
                  const SizedBox(width: 12),
                  _statusBadge('Model', _llmConfig['model'] ?? 'gpt-4o'),
                  const SizedBox(width: 12),
                  _statusBadge('Active Key', maskedKey),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),
        _buildSectionHeader('QUICK PROVIDER PRESETS'),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _presetChip('OpenAI Cloud (gpt-4o)', 'openai', 'https://api.openai.com/v1', 'gpt-4o'),
            _presetChip('Ollama Local (Free / Offline)', 'ollama', 'http://localhost:11434/v1', 'llama3.1'),
            _presetChip('OpenRouter Gateway', 'openrouter', 'https://openrouter.ai/api/v1', 'openai/gpt-4o'),
            _presetChip('DeepSeek API', 'deepseek', 'https://api.deepseek.com/v1', 'deepseek-chat'),
            _presetChip('vLLM / LMStudio', 'custom', 'http://localhost:8000/v1', 'default'),
          ],
        ),

        const SizedBox(height: 24),
        _buildSectionHeader('API CONFIGURATION & ENDPOINT SETTINGS'),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF0C0C0C),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _formFieldLabel('API Base Endpoint URL'),
              const SizedBox(height: 6),
              _styledInput(
                controller: _baseUrlController,
                hintText: 'https://api.openai.com/v1 or http://localhost:11434/v1',
              ),
              const SizedBox(height: 14),
              _formFieldLabel('Model Identifier'),
              const SizedBox(height: 6),
              _styledInput(
                controller: _modelController,
                hintText: 'gpt-4o, llama3.1, deepseek-chat, claude-3-5-sonnet',
              ),
              const SizedBox(height: 14),
              _formFieldLabel('API Key / Secret Token (Saved securely in runtime)'),
              const SizedBox(height: 6),
              TextField(
                controller: _apiKeyController,
                obscureText: _obscureApiKey,
                style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace'),
                decoration: InputDecoration(
                  hintText: hasKey ? 'Key currently set ($maskedKey). Enter new key to update...' : 'sk-... or enter API token',
                  hintStyle: const TextStyle(color: Color(0xFF555555), fontSize: 11),
                  filled: true,
                  fillColor: const Color(0xFF141414),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2E2E2E))),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2E2E2E))),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Colors.white)),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  isDense: true,
                  suffixIcon: IconButton(
                    icon: Icon(_obscureApiKey ? Icons.visibility_off : Icons.visibility, size: 14, color: const Color(0xFF777777)),
                    onPressed: () => setState(() => _obscureApiKey = !_obscureApiKey),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  ElevatedButton.icon(
                    onPressed: _saveLlmConfig,
                    icon: const Icon(Icons.save, size: 14),
                    label: const Text('SAVE & APPLY SETTINGS', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                    ),
                  ),
                  const SizedBox(width: 10),
                  OutlinedButton.icon(
                    onPressed: _fetchLlmConfig,
                    icon: const Icon(Icons.refresh, size: 14),
                    label: const Text('RELOAD CURRENT CONFIG', style: TextStyle(fontSize: 10)),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: Color(0xFF333333)),
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),
        _buildSectionHeader('OPEN SOURCE DEPLOYMENT & LOCAL EXECUTION GUIDE'),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF0A0A0A),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFF1C1C1C)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              Text(
                'Zero-Cost Local AI Setup with Ollama:',
                style: TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 4),
              Text(
                '1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh\n'
                '2. Pull your desired model: ollama run llama3.1\n'
                '3. Click the "Ollama Local" preset chip above and save settings.\n'
                'V.O.I.D.E. connects directly to http://localhost:11434/v1 with zero external cloud dependencies.',
                style: TextStyle(color: Color(0xFF999999), fontSize: 10, height: 1.5, fontFamily: 'monospace'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _statusBadge(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF141414),
        borderRadius: BorderRadius.circular(3),
        border: Border.all(color: const Color(0xFF262626)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('$label: ', style: const TextStyle(color: Color(0xFF777777), fontSize: 9.5)),
          Text(value, style: const TextStyle(color: Colors.white, fontSize: 9.5, fontWeight: FontWeight.bold, fontFamily: 'monospace')),
        ],
      ),
    );
  }

  Widget _presetChip(String label, String provider, String baseUrl, String model) {
    final isSelected = _baseUrlController.text == baseUrl && _modelController.text == model;
    return InkWell(
      onTap: () => _applyPreset(provider, baseUrl, model),
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : const Color(0xFF111111),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: isSelected ? Colors.white : const Color(0xFF282828)),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.black : Colors.white,
            fontSize: 9.5,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  Widget _formFieldLabel(String text) {
    return Text(
      text,
      style: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 10, fontWeight: FontWeight.w600),
    );
  }

  Widget _styledInput({required TextEditingController controller, required String hintText}) {
    return TextField(
      controller: controller,
      style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace'),
      decoration: InputDecoration(
        hintText: hintText,
        hintStyle: const TextStyle(color: Color(0xFF555555), fontSize: 11),
        filled: true,
        fillColor: const Color(0xFF141414),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2E2E2E))),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2E2E2E))),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Colors.white)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        isDense: true,
      ),
    );
  }

  Widget _buildViewportAndTargetsView() {
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        // Status Banner
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: const Color(0xFF0C0C0C),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: Row(
            children: [
              const Icon(Icons.info_outline, size: 14, color: Colors.white),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _statusMessage,
                  style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 10.5, fontFamily: 'monospace'),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),

        // Live Viewport Screenshot Canvas
        _buildSectionHeader('LIVE BROWSER VIEWPORT PREVIEW'),
        const SizedBox(height: 8),
        Container(
          height: 380,
          width: double.infinity,
          decoration: BoxDecoration(
            color: const Color(0xFF0A0A0A),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: _screenshotBytes != null
              ? ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: InteractiveViewer(
                    maxScale: 3.0,
                    child: Image.memory(
                      _screenshotBytes!,
                      fit: BoxFit.contain,
                      gaplessPlayback: true,
                    ),
                  ),
                )
              : Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.web, size: 36, color: Color(0xFF333333)),
                      const SizedBox(height: 10),
                      const Text(
                        'Viewport unmapped or offline',
                        style: TextStyle(color: Color(0xFF666666), fontSize: 11),
                      ),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: () => _launchChromium(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
                        ),
                        child: const Text('Launch Viewport Window', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                      ),
                    ],
                  ),
                ),
        ),

        const SizedBox(height: 16),
        _buildSectionHeader('DISCOVERED SEMANTIC TARGETS'),
        const SizedBox(height: 8),
        _inspectedTargets.isEmpty
            ? Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF0C0C0C),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: const Color(0xFF1E1E1E)),
                ),
                child: const Text('No semantic targets resolved. Click "Discover DOM" to inspect live page.',
                    style: TextStyle(color: Color(0xFF666666), fontSize: 10.5)),
              )
            : Column(
                children: _inspectedTargets.entries.map((e) {
                  final targetName = e.key;
                  final info = e.value is Map ? Map<String, dynamic>.from(e.value) : {'selector': e.value.toString()};
                  return _targetCard(targetName, info);
                }).toList(),
              ),
      ],
    );
  }

  Widget _targetCard(String name, Map<String, dynamic> info) {
    final selector = info['selector'] ?? info['css_selector'] ?? '';
    final confidence = (info['confidence'] ?? 1.0) as num;
    final health = info['health'] ?? 'HEALTHY';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF0E0E0E),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFF222222)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: health == 'HEALTHY' ? const Color(0xFF166534) : const Color(0xFF854D0E),
              borderRadius: BorderRadius.circular(2),
            ),
            child: Text(
              health,
              style: const TextStyle(color: Colors.white, fontSize: 8, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(width: 8),
          Text(name, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              selector.toString(),
              style: const TextStyle(color: Color(0xFF888888), fontSize: 10, fontFamily: 'monospace'),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(
            '${(confidence * 100).toInt()}% conf',
            style: const TextStyle(color: Color(0xFF666666), fontSize: 9.5),
          ),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.center_focus_strong, size: 14, color: Colors.white),
            tooltip: 'Highlight Element',
            splashRadius: 14,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
            onPressed: () => _revealElement(selector.toString(), name),
          ),
          IconButton(
            icon: const Icon(Icons.touch_app, size: 14, color: Colors.white),
            tooltip: 'Simulate Click',
            splashRadius: 14,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
            onPressed: () => _dispatchBrowserAction(selector.toString(), 'click'),
          ),
        ],
      ),
    );
  }

  Widget _buildDomCatalogView() {
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        _buildSectionHeader('DISCOVERED DOM NODES (${_discoveredElements.length} NODES)'),
        const SizedBox(height: 8),
        if (_discoveredElements.isEmpty)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0C0C0C),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFF1E1E1E)),
            ),
            child: const Center(
              child: Text(
                'No elements discovered yet. Navigate to an address and click "Discover DOM".',
                style: TextStyle(color: Color(0xFF666666), fontSize: 11),
              ),
            ),
          )
        else
          ..._discoveredElements.map((el) {
            final m = el is Map ? Map<String, dynamic>.from(el) : <String, dynamic>{};
            final uid = m['uid'] ?? 'el';
            final tag = m['tag'] ?? 'div';
            final text = m['text'] ?? '';
            final id = m['id'] ?? '';
            final role = m['role'] ?? '';
            final selector = id.isNotEmpty ? '#$id' : tag;

            return Container(
              margin: const EdgeInsets.only(bottom: 6),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF0C0C0C),
                borderRadius: BorderRadius.circular(3),
                border: Border.all(color: const Color(0xFF1F1F1F)),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1A1A1A),
                      borderRadius: BorderRadius.circular(2),
                    ),
                    child: Text(
                      tag.toUpperCase(),
                      style: const TextStyle(color: Colors.white, fontSize: 8.5, fontWeight: FontWeight.bold),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(uid, style: const TextStyle(color: Color(0xFF888888), fontSize: 9.5, fontFamily: 'monospace')),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      text.isNotEmpty ? text : (role.isNotEmpty ? 'role=$role' : selector),
                      style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 10),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.flash_on, size: 13, color: Colors.white),
                    tooltip: 'Highlight Node',
                    splashRadius: 12,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 22, minHeight: 22),
                    onPressed: () => _revealElement(selector, uid),
                  ),
                ],
              ),
            );
          }),
      ],
    );
  }

  Widget _buildResolverTelemetryView() {
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        _buildSectionHeader('DOM RESOLVER 8-SIGNAL WEIGHT MATRIX'),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF0C0C0C),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: Column(
            children: const [
              _SignalWeightRow('Semantic Role Match (button, textbox, link)', '0.25', 'Highest priority functional indicator'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('Text Content & Exact Token Overlap', '0.20', 'Labels, text values, inner text'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('ARIA Attributes (aria-label, placeholder)', '0.15', 'Accessibility semantics'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('ID & Name Attribute Similarity', '0.15', 'Stable DOM anchors'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('CSS Class Token Overlap (Jaccard)', '0.10', 'Styling token correlation'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('DOM Hierarchy & Tag Proximity', '0.10', 'DOM depth, parent and neighbor proximity'),
              Divider(color: Color(0xFF1A1A1A)),
              _SignalWeightRow('Geometry & Viewport Bounding Box', '0.05', 'Verifies positive width/height in viewport'),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _buildSectionHeader('CDP RUNTIME & PROFILE TELEMETRY'),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF0C0C0C),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFF222222)),
          ),
          child: Column(
            children: [
              _telemetryRow('Session Profile', _browserStatus['profile_dir'] ?? '~/.config/voide/chromium_profile', 'Local profile directory'),
              const Divider(color: Color(0xFF1A1A1A)),
              _telemetryRow('Active Page', _browserStatus['active_title'] ?? 'None', _browserStatus['active_url'] ?? 'about:blank'),
              const Divider(color: Color(0xFF1A1A1A)),
              _telemetryRow('Open Tabs', '${_browserStatus['tab_count'] ?? 0} page(s)', 'Port 9222 DevTools Protocol'),
              const Divider(color: Color(0xFF1A1A1A)),
              _telemetryRow('Ambiguity Threshold', '< 0.05', 'Triggers AMBIGUOUS health status when candidates tie'),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: Color(0xFF888888),
        fontSize: 9,
        fontWeight: FontWeight.bold,
        letterSpacing: 1.2,
      ),
    );
  }

  Widget _telemetryRow(String title, String val, String subtitle) {
    return Row(
      children: [
        Expanded(
          flex: 2,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)),
              const SizedBox(height: 2),
              Text(subtitle, style: const TextStyle(color: Color(0xFF666666), fontSize: 8.5)),
            ],
          ),
        ),
        Expanded(
          flex: 3,
          child: Text(
            val,
            style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 9.5, fontFamily: 'monospace'),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}

class _SignalWeightRow extends StatelessWidget {
  final String signal;
  final String weight;
  final String rationale;

  const _SignalWeightRow(this.signal, this.weight, this.rationale);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(signal, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(rationale, style: const TextStyle(color: Color(0xFF666666), fontSize: 8.5)),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A1A),
              borderRadius: BorderRadius.circular(3),
            ),
            child: Text(
              'wt $weight',
              style: const TextStyle(color: Colors.white, fontSize: 9.5, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }
}
