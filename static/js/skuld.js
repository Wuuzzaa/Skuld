/* ============================================================
   SKULD — Main JavaScript
   ============================================================ */

/* ── Page Entrance ─────────────────────────────────────────── */
(function () {
    var pw = document.querySelector('.page-wrapper');
    if (!pw) return;
    pw.style.cssText = 'opacity:0;transform:translateY(10px);transition:opacity 0.4s cubic-bezier(0.16,1,0.3,1),transform 0.4s cubic-bezier(0.16,1,0.3,1)';
    requestAnimationFrame(function () {
        requestAnimationFrame(function () {
            pw.style.opacity = '1';
            pw.style.transform = 'translateY(0)';
        });
    });
})();

/* ── Chip Toggle ───────────────────────────────────────────── */
/* Chips are <label class="chip"> wrapping a hidden <input type="checkbox" class="chip-input"> */
document.querySelectorAll('.chip').forEach(function (chip) {
    var input = chip.querySelector('.chip-input');
    if (!input) return;

    // Sync initial state
    if (input.checked) {
        chip.classList.add('active');
        if (chip.classList.contains('chip-green')) chip.classList.add('active-green');
    }

    chip.addEventListener('click', function (e) {
        if (e.target === input) return; // native toggle already happened
        input.checked = !input.checked;
        
        // Handle normal .active chips and special .chip-green chips
        if (chip.classList.contains('chip-green')) {
            chip.classList.toggle('active-green', input.checked);
            chip.classList.toggle('active', input.checked);
        } else {
            chip.classList.toggle('active', input.checked);
        }
        
        // Manual dispatch to trigger onchange/global listeners
        input.dispatchEvent(new Event('change', { bubbles: true }));
        // Ripple
        _ripple(chip);
    });

    input.addEventListener('change', function () {
        if (chip.classList.contains('chip-green')) {
            chip.classList.toggle('active-green', input.checked);
            chip.classList.toggle('active', input.checked);
        } else {
            chip.classList.toggle('active', input.checked);
        }
    });
});

/* ── Ripple Effect ─────────────────────────────────────────── */
function _ripple(el) {
    var r = document.createElement('span');
    r.style.cssText = [
        'position:absolute',
        'border-radius:50%',
        'background:rgba(74,158,255,0.25)',
        'width:60px', 'height:60px',
        'margin-top:-30px', 'margin-left:-30px',
        'top:50%', 'left:50%',
        'transform:scale(0)',
        'animation:ripple-anim 0.4s ease-out forwards',
        'pointer-events:none'
    ].join(';');
    el.style.position = 'relative';
    el.style.overflow = 'hidden';
    el.appendChild(r);
    setTimeout(function () { r.remove(); }, 450);
}

// Inject ripple keyframes once
(function () {
    if (document.getElementById('skuld-ripple-style')) return;
    var s = document.createElement('style');
    s.id = 'skuld-ripple-style';
    s.textContent = '@keyframes ripple-anim{to{transform:scale(2.5);opacity:0}}';
    document.head.appendChild(s);
})();

/* ── Auto-submit on filter change ──────────────────────────── */
document.addEventListener('change', function (e) {
    var form = e.target.closest('form.auto-submit');
    if (!form) return;
    if (e.target.matches('select, input[type="checkbox"]')) {
        form.submit();
    }
});

/* ── Number Coloring ───────────────────────────────────────── */
function colorNumbers() {
    document.querySelectorAll('table.skuld-table tbody td').forEach(function (td) {
        var t = td.textContent.trim();
        if (/^-[\d,]+(\.\d+)?(%)?$/.test(t) || /^\([\d,.]+\)$/.test(t)) {
            td.classList.add('val-negative');
        } else if (/^\+[\d,]+(\.\d+)?(%)?$/.test(t)) {
            td.classList.add('val-positive');
        }
    });
}

/* ── DataTables Init ───────────────────────────────────────── */
$(document).ready(function () {

    $('table.skuld-table').each(function () {
        var $t = $(this);
        var pageLen = parseInt($t.data('page-length') || 25);

        var dt = $t.DataTable({
            pageLength: pageLen,
            lengthMenu: [10, 25, 50, 100, 250],
            order: [],
            scrollX: false,
            autoWidth: true,
            dom: '<"dt-top-bar"lf>t<"dt-bottom-bar"ip>',
            language: {
                search: '',
                searchPlaceholder: 'Search…',
                lengthMenu: '_MENU_ rows',
                info: '_START_–_END_ of _TOTAL_',
                infoEmpty: '0 results',
                paginate: { first: '«', last: '»', next: '›', previous: '‹' },
                emptyTable: 'No data',
                zeroRecords: 'No matching records'
            }
        });

        // Color numbers after each draw
        dt.on('draw', colorNumbers);
    });

    // Initial coloring for non-DataTable tables
    colorNumbers();

    /* ── Select2 ─────────────────────────────────────────────── */
    $('select.skuld-select2').each(function () {
        $(this).select2({
            theme: 'default',
            width: '100%',
            dropdownParent: $(this).closest('form').length ? $(this).closest('form') : $('body')
        });
    });

    /* ── Tooltips ────────────────────────────────────────────── */
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
        new bootstrap.Tooltip(el, { trigger: 'hover' });
    });

    /* ── Keyboard Shortcut: / → focus DataTables search ─────── */
    document.addEventListener('keydown', function (e) {
        if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            e.preventDefault();
            var searchInput = document.querySelector('.dataTables_filter input');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }
        // Escape → blur
        if (e.key === 'Escape') {
            document.activeElement.blur();
        }
    });

    /* ── Stat pill: live result count update ─────────────────── */
    var $countEl = $('#result-count-live');
    if ($countEl.length) {
        $('table.skuld-table').on('draw.dt', function () {
            var info = $(this).DataTable().page.info();
            $countEl.text(info.recordsDisplay);
        });
    }

    /* ── Stagger module cards on index ──────────────────────── */
    document.querySelectorAll('.module-card').forEach(function (card, i) {
        card.style.opacity = '0';
        card.style.transform = 'translateY(12px)';
        card.style.transition = 'opacity 0.4s cubic-bezier(0.16,1,0.3,1), transform 0.4s cubic-bezier(0.16,1,0.3,1), border-color 0.2s, box-shadow 0.2s';
        setTimeout(function () {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 80 + i * 45);
    });

    /* ── Live clock in footer ────────────────────────────────── */
    var clockEl = document.getElementById('footer-clock');
    if (clockEl) {
        function tick() {
            var now = new Date();
            clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
        }
        tick();
        setInterval(tick, 1000);
    }

});
