import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voide_desktop/main.dart';

void main() {
  testWidgets('V.O.I.D.E. Desktop Shell mounts three-panel workspace and switches workstation tabs', (WidgetTester tester) async {
    // Configure desktop viewport dimensions
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const VoideApp());
    // Allow connection timeout timer to elapse cleanly
    await tester.pump(const Duration(seconds: 4));

    // Verify Brand, Command Bar, and Panels
    expect(find.text('V.O.I.D.E.'), findsOneWidget);
    expect(find.text('WORKSPACE'), findsOneWidget);
    expect(find.text('AGENT INTELLIGENCE'), findsOneWidget);

    // Verify default view is Overview
    expect(find.text('Facility Chiller Anomaly & Evidence Workstation'), findsOneWidget);

    // Switch to Data tab
    await tester.tap(find.byTooltip('Data Ingestion & Profiling'));
    await tester.pump();
    expect(find.text('UNIVERSAL DATASET INGESTION & PROFILING'), findsOneWidget);

    // Switch to Analysis tab
    await tester.tap(find.byTooltip('Contextual Analysis & Baseline'));
    await tester.pump();
    expect(find.text('CONTEXTUAL ML ANALYSIS & RESIDUAL MODELING'), findsOneWidget);

    // Switch to Investigation tab
    await tester.tap(find.byTooltip('Investigation & Evidence Chain'));
    await tester.pump();
    expect(find.text('RANKED ANOMALIES'), findsOneWidget);

    // Switch to Visuals tab
    await tester.tap(find.byTooltip('Visual Intelligence & Schematics'));
    await tester.pump();
    expect(find.text('VISUAL INTELLIGENCE & ENGINEERING SCHEMATICS'), findsOneWidget);

    // Switch to Reports tab
    await tester.tap(find.byTooltip('Engineering Reports'));
    await tester.pump();
    expect(find.text('ENGINEERING REPORT & EXPLAINABILITY'), findsOneWidget);
  });
}
