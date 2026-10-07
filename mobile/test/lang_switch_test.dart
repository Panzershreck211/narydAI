import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/app.dart';
import 'package:naryad_ai/core/i18n/i18n.dart';
import 'package:naryad_ai/core/realtime/realtime_service.dart';
import 'package:naryad_ai/features/auth/data/auth_repository.dart';
import 'package:naryad_ai/features/auth/domain/app_user.dart';
import 'package:naryad_ai/features/orders/data/orders_repository.dart';
import 'package:naryad_ai/features/orders/domain/work_order.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// Рабочий уже вошёл.
class _Session implements AuthRepository {
  @override
  Future<AppUser?> restore() async => AppUser.fromJson({
    'id': 5,
    'login': '1002',
    'fio': 'Жумабаев Нурлан Канатович',
    'role': 'executor',
    'on_shift': true,
  });

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Нарядов нет — сеть в тесте не нужна.
class _NoOrders implements OrdersRepository {
  @override
  Future<List<WorkOrder>> list({List<OrderStatus>? statuses}) async => [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  testWidgets(
    'смена языка переводит весь экран, включая неизменяемые (const) виджеты',
    (tester) async {
      final container = ProviderContainer(
        overrides: [
          authRepositoryProvider.overrideWithValue(_Session()),
          ordersRepositoryProvider.overrideWithValue(_NoOrders()),
          realtimeServiceProvider.overrideWithValue(null),
        ],
      );
      addTearDown(container.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const NaryadApp(),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Помощник'), findsOneWidget);
      expect(find.text('Нарядов нет'), findsOneWidget);

      await container.read(langProvider.notifier).set(AppLang.kk);
      await tester.pumpAndSettle();

      // кнопка «Помощник» — const-виджет: раньше она оставалась по-русски
      expect(find.text('Көмекші'), findsOneWidget);
      expect(find.text('Нарядтар жоқ'), findsOneWidget);
      expect(find.text('Помощник'), findsNothing);

      await container.read(langProvider.notifier).set(AppLang.ru);
      await tester.pumpAndSettle();
      expect(find.text('Помощник'), findsOneWidget);
      expect(find.text('Көмекші'), findsNothing);
    },
  );
}
