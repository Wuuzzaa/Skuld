/* ============================================================
   SKULD 2026 — Main JavaScript
   ============================================================ */

$(document).ready(function () {

    // ── DataTables Init ──────────────────────────────────────
    $('table.skuld-table').each(function () {
        var $table = $(this);
        var pageLen = parseInt($table.data('page-length') || 25);

        $table.DataTable({
            pageLength: pageLen,
            lengthMenu: [10, 25, 50, 100, 250],
            order: [],
            scrollX: true,
            autoWidth: false,
            dom: '<"dt-top-bar"lf>t<"dt-bottom-bar"ip>',
            language: {
                search:          '',
                searchPlaceholder: 'Filter results...',
                lengthMenu:      '_MENU_ rows',
                info:            '_START_–_END_ of _TOTAL_',
                infoEmpty:       '0 results',
                paginate: {
                    first:    '«',
                    last:     '»',
                    next:     '›',
                    previous: '‹'
                },
                emptyTable:   'No data available',
                zeroRecords:  'No matching records'
            }
        });
    });

    // ── Select2 Init ─────────────────────────────────────────
    $('select.skuld-select2').each(function () {
        $(this).select2({
            theme: 'default',
            width: '100%',
            dropdownParent: $(this).closest('form').length ? $(this).closest('form') : $('body')
        });
    });

    // ── Auto-submit on filter change ─────────────────────────
    $(document).on('change', 'form.auto-submit select, form.auto-submit input[type="checkbox"]', function () {
        $(this).closest('form').submit();
    });

    // ── Highlight negative numbers in table cells ────────────
    $('table.skuld-table tbody td').each(function () {
        var text = $(this).text().trim();
        if (/^-[\d,]+(\.\d+)?(%)?$/.test(text) || /^\([\d,]+(\.\d+)?\)$/.test(text)) {
            $(this).addClass('val-negative');
        } else if (/^\+[\d,]+(\.\d+)?(%)?$/.test(text)) {
            $(this).addClass('val-positive');
        }
    });

    // ── Tooltip init ─────────────────────────────────────────
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
        new bootstrap.Tooltip(el, { trigger: 'hover' });
    });

    // ── Fade-in page content ─────────────────────────────────
    document.querySelector('.page-wrapper') && (function () {
        var pw = document.querySelector('.page-wrapper');
        pw.style.opacity = '0';
        pw.style.transform = 'translateY(6px)';
        pw.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                pw.style.opacity = '1';
                pw.style.transform = 'translateY(0)';
            });
        });
    })();

});
