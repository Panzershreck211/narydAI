import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/common.dart';
import '../../auth/application/auth_controller.dart';
import '../../orders/application/orders_providers.dart';
import '../../orders/presentation/order_detail_screen.dart';
import '../../orders/presentation/widgets/order_card.dart';
import '../../references/data/references_repository.dart';
import '../../references/domain/references.dart';

final executorsProvider = FutureProvider.autoDispose<List<ExecutorStatus>>(
  (ref) => ref.watch(referencesRepositoryProvider).executors(),
);

/// Доска мастера: счётчики смены, статусы исполнителей, канбан.
class BoardScreen extends ConsumerWidget {
  const BoardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final board = ref.watch(boardProvider);

    Future<void> refresh() async {
      ref.invalidate(countersProvider);
      ref.invalidate(executorsProvider);
      ref.invalidate(boardProvider);
      await ref.read(boardProvider.future);
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Доска нарядов'),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            onPressed: () => context.push('/notifications'),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/board/new'),
        icon: const Icon(Icons.add),
        label: const Text('Наряд'),
      ),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(child: _Counters()),
            const SliverToBoxAdapter(child: _Executors()),
            SliverFillRemaining(
              child: AsyncView(
                value: board,
                onRetry: refresh,
                data: (columns) => ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.all(8),
                  children: [
                    for (final entry in columns.entries)
                      _Column(title: entry.key, orders: entry.value),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Counters extends ConsumerWidget {
  const _Counters();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = ref.watch(countersProvider).asData?.value ?? const {};
    Widget tile(String label, String key, Color color) => Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Column(
            children: [
              Text(
                '${c[key] ?? '–'}',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(
                label,
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: [
          tile('Выдано', 'issued', Colors.blueGrey),
          tile('Выполнено', 'completed', Colors.green),
          tile('Просрочено', 'overdue', Colors.red),
          tile('Простой', 'equipment_down', Colors.orange),
        ],
      ),
    );
  }
}

class _Executors extends ConsumerWidget {
  const _Executors();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final list = ref.watch(executorsProvider).asData?.value ?? const [];
    return SizedBox(
      height: 44,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        children: [
          for (final e in list)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Chip(
                avatar: AvailabilityDot(e.availability),
                label: Text(
                  '${e.fio.split(' ').first} · ${e.availability.label}',
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Column extends StatelessWidget {
  const _Column({required this.title, required this.orders});
  final String title;
  final List orders;

  @override
  Widget build(BuildContext context) => Container(
    width: 290,
    margin: const EdgeInsets.only(right: 8),
    decoration: BoxDecoration(
      color: Theme.of(
        context,
      ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(10),
          child: Text(
            '$title (${orders.length})',
            style: Theme.of(context).textTheme.titleSmall,
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            children: [
              for (final o in orders)
                OrderCard(
                  order: o,
                  compact: true,
                  onTap: () => context.push('/orders/${o.id}'),
                ),
            ],
          ),
        ),
      ],
    ),
  );
}
