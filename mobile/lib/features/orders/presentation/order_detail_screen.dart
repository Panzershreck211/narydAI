import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/config.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/app_user.dart';
import '../../references/data/references_repository.dart';
import '../../references/domain/references.dart';
import '../application/orders_providers.dart';
import '../data/orders_repository.dart';
import '../domain/work_order.dart';
import 'widgets/order_card.dart';

class OrderDetailScreen extends ConsumerStatefulWidget {
  const OrderDetailScreen({super.key, required this.orderId});
  final int orderId;

  @override
  ConsumerState<OrderDetailScreen> createState() => _OrderDetailScreenState();
}

class _OrderDetailScreenState extends ConsumerState<OrderDetailScreen> {
  bool _busy = false;

  OrdersRepository get _repo => ref.read(ordersRepositoryProvider);

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(orderDetailProvider(widget.orderId));
      ref.invalidate(myOrdersProvider);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _onAction(OrderAction action) async {
    switch (action) {
      case OrderAction.complete:
        context.push('/orders/${widget.orderId}/close');
      case OrderAction.approve:
        final score = await _askScore();
        if (score != null) {
          await _run(() => _repo.approve(widget.orderId, score));
        }
      case OrderAction.reassign:
        final executor = await _pickExecutor();
        if (executor != null) {
          await _run(
            () => _repo.reassign(widget.orderId, executorId: executor),
          );
        }
      default:
        String? reason;
        if (action.needsReason) {
          reason = await askReason(context, action.label);
          if (reason == null) return;
        }
        await _run(() => _repo.action(widget.orderId, action, reason: reason));
    }
  }

  Future<void> _addPhoto({required bool after}) async {
    final picker = ImagePicker();
    final photo = await picker.pickImage(
      source: ImageSource.camera,
      maxWidth: 1920,
      imageQuality: 85,
    );
    if (photo == null) return;
    await _run(
      () => _repo.uploadPhotos(widget.orderId, after: after, files: [photo]),
    );
  }

  Future<int?> _askScore() => showDialog<int>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: const Text('Оценка качества работы'),
      children: [
        for (var s = 5; s >= 1; s--)
          SimpleDialogOption(
            onPressed: () => Navigator.pop(ctx, s),
            child: Row(
              children: [
                for (var i = 0; i < s; i++)
                  const Icon(Icons.star, color: Colors.amber),
              ],
            ),
          ),
      ],
    ),
  );

  Future<int?> _pickExecutor() async {
    final list = await ref.read(referencesRepositoryProvider).executors();
    if (!mounted) return null;
    return showModalBottomSheet<int>(
      context: context,
      builder: (ctx) => ListView(
        children: [
          for (final e in list)
            ListTile(
              leading: AvailabilityDot(e.availability),
              title: Text(e.fio),
              subtitle: Text('${e.specialty ?? ''} · ${e.availability.label}'),
              onTap: () => Navigator.pop(ctx, e.id),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(orderDetailProvider(widget.orderId));
    final role = ref.watch(currentUserProvider)?.role;

    return Scaffold(
      appBar: AppBar(title: Text(detail.asData?.value.order.number ?? 'Наряд')),
      body: AsyncView(
        value: detail,
        onRetry: () => ref.invalidate(orderDetailProvider(widget.orderId)),
        data: (d) => Stack(
          children: [
            RefreshIndicator(
              onRefresh: () =>
                  ref.refresh(orderDetailProvider(widget.orderId).future),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 120),
                children: [
                  OrderCard(order: d.order),
                  _InfoSection(detail: d),
                  _PhotosSection(
                    photos: d.photos,
                    canAddBefore:
                        d.order.status.isActive && role != Role.manager,
                    canAddAfter:
                        role == Role.executor &&
                        (d.order.status == OrderStatus.inProgress ||
                            d.order.status == OrderStatus.paused),
                    onAdd: (after) => _addPhoto(after: after),
                  ),
                  if (d.aiReport != null) _AiSection(report: d.aiReport!),
                  _HistorySection(events: d.events),
                ],
              ),
            ),
            if (_busy) const LinearProgressIndicator(),
          ],
        ),
      ),
      bottomNavigationBar: switch (detail) {
        AsyncValue(:final value?) when value.order.allowedActions.isNotEmpty =>
          Container(
            decoration: BoxDecoration(
              color: context.colors.surface,
              border: Border(top: BorderSide(color: context.colors.border)),
            ),
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: [
                    for (final a in value.order.allowedActions)
                      _ActionButton(
                        action: a,
                        onPressed: _busy ? null : () => _onAction(a),
                      ),
                  ],
                ),
              ),
            ),
          ),
        _ => null,
      },
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({required this.action, required this.onPressed});
  final OrderAction action;
  final VoidCallback? onPressed;

  static const _primary = {
    OrderAction.accept,
    OrderAction.start,
    OrderAction.complete,
    OrderAction.approve,
  };
  static const _danger = {OrderAction.reject, OrderAction.cancel};

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final icon = Icon(action.icon, size: 20);
    final label = Text(action.label);
    if (_primary.contains(action)) {
      return FilledButton.icon(onPressed: onPressed, icon: icon, label: label);
    }
    if (_danger.contains(action)) {
      return OutlinedButton.icon(
        onPressed: onPressed,
        icon: icon,
        label: label,
        style: OutlinedButton.styleFrom(
          foregroundColor: c.red,
          side: BorderSide(color: c.red.withValues(alpha: 0.5)),
        ),
      );
    }
    return OutlinedButton.icon(onPressed: onPressed, icon: icon, label: label);
  }
}

/// Секция карточки — как .drawer__section в панели.
class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.child,
    this.accent,
    this.trailing,
  });
  final String title;
  final Widget child;
  final Color? accent;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (accent != null) Container(width: 4, color: accent),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            title,
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 14,
                              color: accent ?? c.text,
                            ),
                          ),
                        ),
                        ?trailing,
                      ],
                    ),
                    const SizedBox(height: 10),
                    child,
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

class _InfoSection extends StatelessWidget {
  const _InfoSection({required this.detail});
  final OrderDetail detail;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final o = detail.order;
    Widget row(String k, String? v, {Color? color}) => v == null
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 118,
                  child: Text(k, style: TextStyle(color: c.muted)),
                ),
                Expanded(
                  child: Text(v, style: TextStyle(color: color ?? c.text)),
                ),
              ],
            ),
          );
    return _Section(
      title: 'Сведения',
      child: Column(
        children: [
          row('Тип', o.type.label, color: o.isEmergency ? c.red : null),
          row(
            'Приоритет',
            o.priority.label,
            color: priorityColor(context, o.priority),
          ),
          row('Участок', o.workshopName),
          row('Оборудование', o.equipmentName),
          row(
            'Состояние',
            o.equipmentStopped ? 'Оборудование остановлено' : null,
            color: c.amber,
          ),
          row('Мастер', o.master.fio),
          row('Исполнитель', o.executor?.fio ?? 'Бригада (не взят)'),
          row(
            'Срок',
            o.status.isActive
                ? '${dateTimeFmt.format(o.deadline)} · ${timeLeft(o.deadline)}'
                : dateTimeFmt.format(o.deadline),
            color: o.isOverdue ? c.red : null,
          ),
          row('Выдан', dateTimeFmt.format(o.createdAt)),
          if (detail.workReport != null) ...[
            Divider(height: 20, color: c.border),
            row('Выполнено', detail.workReport),
            row('Шифр', detail.faultCode),
            if (detail.materials.isNotEmpty)
              row(
                'Материалы',
                detail.materials
                    .map((m) => '${m.name} — ${_qty(m.quantity)} ${m.unit}')
                    .join('\n'),
              ),
          ],
        ],
      ),
    );
  }
}

class _PhotosSection extends StatelessWidget {
  const _PhotosSection({
    required this.photos,
    required this.canAddBefore,
    required this.canAddAfter,
    required this.onAdd,
  });

  final List<OrderPhoto> photos;
  final bool canAddBefore;
  final bool canAddAfter;
  final void Function(bool after) onAdd;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    Widget strip(String title, bool after, bool canAdd) {
      final list = photos.where((p) => p.isAfter == after).toList();
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title.toUpperCase(),
            style: TextStyle(
              color: c.muted,
              fontSize: 11.5,
              letterSpacing: 0.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 84,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (final p in list)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.network(
                        AppConfig.mediaUrl(p.url),
                        width: 84,
                        height: 84,
                        fit: BoxFit.cover,
                      ),
                    ),
                  ),
                if (canAdd && list.length < 5)
                  InkWell(
                    onTap: () => onAdd(after),
                    borderRadius: BorderRadius.circular(8),
                    child: Container(
                      width: 84,
                      height: 84,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: c.border, width: 2),
                      ),
                      child: Icon(Icons.add_a_photo_outlined, color: c.muted),
                    ),
                  ),
                if (list.isEmpty && !canAdd)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text('нет', style: TextStyle(color: c.muted)),
                  ),
              ],
            ),
          ),
        ],
      );
    }

    return _Section(
      title: 'Фото',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          strip('До', false, canAddBefore),
          const SizedBox(height: 12),
          strip('После', true, canAddAfter),
        ],
      ),
    );
  }
}

class _AiSection extends StatelessWidget {
  const _AiSection({required this.report});
  final AiReport report;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final accent = switch (report.verdict) {
      'ok' => c.green,
      'needs_review' => c.amber,
      _ => c.red,
    };
    final warnings = report.checks.where(
      (x) => x.severity == 'warn' || x.severity == 'error',
    );
    return _Section(
      title: '✦ ИИ-проверка: ${report.verdictLabel}',
      accent: accent,
      trailing: Text(
        '${report.score.toStringAsFixed(1)}/5',
        style: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: c.text,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            [
              report.source == 'rules+llm' ? 'Правила + LLM' : 'Правила',
              if (report.photoScore != null)
                'качество фото ${report.photoScore!.toStringAsFixed(1)}/5',
            ].join(' · '),
            style: TextStyle(color: c.muted, fontSize: 12.5),
          ),
          for (final w in warnings)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    w.severity == 'error'
                        ? Icons.cancel_outlined
                        : Icons.warning_amber_rounded,
                    size: 17,
                    color: w.severity == 'error' ? c.red : c.amber,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(w.message, style: TextStyle(color: c.text)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

const _eventLabels = {
  'create': 'Наряд выдан',
  'accept': 'Принят в работу',
  'queue': 'Поставлен в очередь',
  'reject': 'Отклонён',
  'start': 'Начато исполнение',
  'pause': 'Приостановлен',
  'complete': 'Исполнено',
  'approve': 'Работа принята',
  'return': 'Возвращён на доработку',
  'reassign': 'Переназначен',
  'cancel': 'Отменён',
  'update': 'Изменён',
  'photo': 'Добавлены фото',
  'reminder': 'ИИ: напоминание о сроке',
  'overdue': 'ИИ: просрочка',
  'risk': 'ИИ: риск просрочки',
  'ai_check': 'ИИ-проверка',
};

class _HistorySection extends StatelessWidget {
  const _HistorySection({required this.events});
  final List<OrderEvent> events;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return _Section(
      title: 'История',
      child: Column(
        children: [
          for (final e in events.reversed)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 84,
                    child: Text(
                      dateTimeFmt.format(e.timestamp),
                      style: TextStyle(color: c.muted, fontSize: 12),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _eventLabels[e.action] ?? e.action,
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: e.userName == null ? c.primary : c.text,
                          ),
                        ),
                        Text(
                          [e.userName ?? 'ИИ-система', ?e.reason].join(' · '),
                          style: TextStyle(color: c.muted, fontSize: 12.5),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class AvailabilityDot extends StatelessWidget {
  const AvailabilityDot(this.availability, {super.key});
  final Availability availability;

  /// Цвета из ТЗ: зелёный — свободен, жёлтый — в работе, синий — очередь, серый — не на смене.
  static Color colorOf(Availability a) => switch (a) {
    Availability.free => const Color(0xFF43A047),
    Availability.busy => const Color(0xFFFBC02D),
    Availability.queued => const Color(0xFF1E88E5),
    Availability.offShift => const Color(0xFF9E9E9E),
  };

  @override
  Widget build(BuildContext context) =>
      CircleAvatar(radius: 7, backgroundColor: colorOf(availability));
}

/// 1.0 → «1», 0.5 → «0.5»
String _qty(double q) =>
    q == q.roundToDouble() ? q.toInt().toString() : q.toString();
