import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/common.dart';
import '../../domain/work_order.dart';

/// Цвета бейджа статуса — как .badge--* в панели.
(Color bg, Color fg) statusColors(BuildContext context, OrderStatus s) {
  final c = context.colors;
  final dark = Theme.of(context).brightness == Brightness.dark;
  return switch (s) {
    OrderStatus.issued => (c.surface2, c.muted),
    OrderStatus.accepted => (
      dark ? c.surface2 : const Color(0xFFE3F0FD),
      dark ? const Color(0xFF64B5F6) : const Color(0xFF1565C0),
    ),
    OrderStatus.queued => (
      dark ? c.surface2 : const Color(0xFFE8EAF8),
      dark ? const Color(0xFF9FA8DA) : const Color(0xFF3949AB),
    ),
    OrderStatus.inProgress => (
      c.amberSoft,
      dark ? c.amber : const Color(0xFFA86F00),
    ),
    OrderStatus.paused => (
      dark ? c.surface2 : const Color(0xFFFDEEE7),
      dark ? const Color(0xFFFF8A65) : const Color(0xFFD84315),
    ),
    OrderStatus.completed || OrderStatus.closed => (c.greenSoft, c.green),
    OrderStatus.rejected => (c.redSoft, c.red),
    OrderStatus.cancelled => (c.surface2, c.grey),
  };
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key});
  final OrderStatus status;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = statusColors(context, status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        status.label,
        style: TextStyle(color: fg, fontWeight: FontWeight.w600, fontSize: 12),
      ),
    );
  }
}

/// Маленькая метка: «АВАРИЙНЫЙ», «простой», «просрочен».
class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, required this.bg, required this.fg});
  final String text;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
    decoration: BoxDecoration(
      color: bg,
      borderRadius: BorderRadius.circular(4),
    ),
    child: Text(
      text,
      style: TextStyle(
        color: fg,
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.2,
      ),
    ),
  );
}

Color priorityColor(BuildContext context, Priority p) {
  final c = context.colors;
  return switch (p) {
    Priority.critical => c.red,
    Priority.high => c.orange,
    _ => c.muted,
  };
}

/// Карточка наряда — как .ocard в панели: аварийные с красной полосой слева, просроченные подсвечены.
class OrderCard extends StatelessWidget {
  const OrderCard({
    super.key,
    required this.order,
    this.onTap,
    this.compact = false,
  });

  final WorkOrder order;
  final VoidCallback? onTap;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final done =
        order.status == OrderStatus.completed ||
        order.status == OrderStatus.closed;
    final bg = order.isOverdue
        ? Color.alphaBlend(c.redSoft.withValues(alpha: 0.6), c.surface)
        : c.surface;

    return Card(
      color: bg,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (order.isEmergency) Container(width: 4, color: c.red),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          if (order.isEmergency) ...[
                            Tag('АВАРИЙНЫЙ', bg: c.red, fg: Colors.white),
                            const SizedBox(width: 6),
                          ],
                          Expanded(
                            child: Text(
                              order.number,
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                                color: c.text,
                              ),
                            ),
                          ),
                          StatusChip(order.status),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        order.description,
                        maxLines: compact ? 2 : 3,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 15,
                          color: c.text,
                          height: 1.3,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(
                            order.equipmentName ?? order.workshopName,
                            style: TextStyle(fontSize: 12, color: c.muted),
                          ),
                          if (order.equipmentStopped)
                            Tag('простой', bg: c.amberSoft, fg: c.amber),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Icon(
                            Icons.schedule,
                            size: 15,
                            color: order.isOverdue ? c.red : c.muted,
                          ),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              done
                                  ? 'до ${dateTimeFmt.format(order.deadline)}'
                                  : timeLeft(order.deadline),
                              style: TextStyle(
                                fontSize: 12.5,
                                color: order.isOverdue ? c.red : c.text,
                                fontWeight: order.isOverdue
                                    ? FontWeight.w700
                                    : FontWeight.w400,
                              ),
                            ),
                          ),
                          Text(
                            order.priority.label,
                            style: TextStyle(
                              fontSize: 12,
                              color: priorityColor(context, order.priority),
                              fontWeight:
                                  order.priority.index >= Priority.high.index
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                          ),
                        ],
                      ),
                      if (compact) ...[
                        const SizedBox(height: 4),
                        Text(
                          order.executor?.fio ?? 'Бригада — ещё не взят',
                          style: TextStyle(fontSize: 12, color: c.muted),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
