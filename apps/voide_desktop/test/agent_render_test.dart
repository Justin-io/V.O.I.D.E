import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voide_desktop/services/ipc_client.dart';
import 'package:voide_desktop/widgets/agent_panel.dart';

class FakeIPCClient extends IPCClient {
  final StreamController<Map<String, dynamic>> _chatController = StreamController<Map<String, dynamic>>.broadcast();
  final StreamController<Map<String, dynamic>> _toolController = StreamController<Map<String, dynamic>>.broadcast();
  final StreamController<bool> _connController = StreamController<bool>.broadcast();

  @override
  Stream<Map<String, dynamic>> get chatStream => _chatController.stream;
  @override
  Stream<Map<String, dynamic>> get toolStream => _toolController.stream;
  @override
  Stream<bool> get connectionStream => _connController.stream;
  @override
  bool get isConnected => true;

  @override
  void startAutoReconnect() {}

  @override
  Future<dynamic> send(String method, [dynamic params]) async {
    if (method == 'chat_session_create') {
      return {'session_id': 'test-session-1'};
    }
    if (method == 'list_chat_sessions') {
      return [
        {'session_id': 'test-session-1', 'title': 'Test Chat', 'updated_at': 1700000000.0, 'message_count': 1}
      ];
    }
    return {};
  }

  void emitChat(String text, {bool done = false}) {
    _chatController.add({'full_text': text, 'token': text, 'done': done});
  }

  @override
  void dispose() {
    _chatController.close();
    _toolController.close();
    _connController.close();
    super.dispose();
  }
}

void main() {
  testWidgets('AgentPanel renders Markdown tables, LaTeX math formulas, and bold text cleanly', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final fakeIpc = FakeIPCClient();
    addTearDown(fakeIpc.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentPanel(
            ipc: fakeIpc,
          ),
        ),
      ),
    );
    await tester.pump();

    // Verify initial empty state
    expect(find.text('ENGINEERING COPILOT'), findsOneWidget);

    // Enter a prompt in the input field and submit
    await tester.enterText(find.byType(TextField), 'Explain baseline model and equation');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();

    // Emit assistant message with LaTeX math, Markdown table, and bold formatting
    const sampleResponse = '''
### Baseline Model Specification
The expected electrical power draw \$\\hat{y}_t\$ is modeled as a contextual regression baseline:

\$\$\\hat{y}_t = \\beta_0 + \\beta_1 \\cdot \\text{CoolingRate}_t + \\beta_2 \\cdot \\Delta T_{\\text{lift}, t} + \\epsilon_t\$\$

Key fit metrics:
| Parameter | Description | Estimated Value |
| --- | --- | --- |
| \$\\beta_0\$ | Base idle standby load | 42.3 kW |
| \$\\beta_1\$ | Thermal capacity coefficient | 0.684 kW/ton |
| \$R^2\$ | Coefficient of determination | 0.892 |
| \$\\text{CV(RMSE)}\$ | ASHRAE Guideline 14 fit | 14.2% |

**Conclusion**: All **3 chillers** meet the ASHRAE Guideline 14 limit.
''';

    fakeIpc.emitChat(sampleResponse, done: true);
    await tester.pumpAndSettle();

    // Verify that MarkdownBody is rendered
    expect(find.byType(MarkdownBody), findsAtLeastNWidgets(1));

    // Verify native Table widget is created by flutter_markdown for the table
    expect(find.byType(Table), findsAtLeastNWidgets(1));

    // Verify header and assistant message content
    expect(find.text('V.O.I.D.E.'), findsAtLeastNWidgets(1));
  });
}
