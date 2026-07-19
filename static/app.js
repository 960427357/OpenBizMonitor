// 全局数据
let allRecords = [];

// HTML转义函数（防XSS）
function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}

// 加载所有数据
function loadAllRecords() {
    fetch('/api/search?q=')
        .then(r => r.json())
        .then(records => {
            allRecords = records;
            populateAreaFilter(records);
            applyFilters();
        });
}

// 填充区域筛选下拉框
function populateAreaFilter(records) {
    const areaSet = new Set();
    records.forEach(r => {
        if (r.area) {
            const areas = r.area.split('-');
            areaSet.add(areas[areas.length - 1]);
        }
    });

    const select = document.getElementById('filterArea');
    select.innerHTML = '<option value="">全部区域</option>';
    Array.from(areaSet).sort().forEach(area => {
        const opt = document.createElement('option');
        opt.value = area;
        opt.textContent = area;
        select.appendChild(opt);
    });
}

// 应用筛选
function applyFilters() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const filterArea = document.getElementById('filterArea').value;
    const filterStatus = document.getElementById('filterStatus').value;
    const filterTime = parseInt(document.getElementById('filterTime').value) || 0;

    let filtered = allRecords.filter(record => {
        if (query) {
            const searchText = (record.name + ' ' + (record.address || '') + ' ' + (record.legal_person || '')).toLowerCase();
            if (!searchText.includes(query)) return false;
        }

        if (filterArea) {
            const areas = (record.area || '').split('-');
            const areaDisplay = areas[areas.length - 1] || '';
            if (areaDisplay !== filterArea) return false;
        }

        if (filterStatus && record.status !== filterStatus) {
            return false;
        }

        if (filterTime && record.establish_date) {
            try {
                const establishDate = new Date(record.establish_date);
                const cutoffDate = new Date();
                cutoffDate.setDate(cutoffDate.getDate() - filterTime);
                if (establishDate < cutoffDate) return false;
            } catch (e) {
                // 日期解析失败则不过滤
            }
        }

        return true;
    });

    updateTable(filtered);
}

function searchRecords() {
    applyFilters();
}

function resetFilters() {
    document.getElementById('searchInput').value = '';
    document.getElementById('filterArea').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('filterTime').value = '';
    applyFilters();
}

// 更新表格
function updateTable(records) {
    const tbody = document.getElementById('recordsTable');
    tbody.innerHTML = '';

    if (records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center py-4">没有找到符合条件的记录</td></tr>';
        return;
    }

    records.forEach(record => {
        const row = document.createElement('tr');
        row.dataset.id = record.id;

        const statusClass = record.status === '筹建审批中' ? 'status-pending' :
                           record.status === '已排除' ? 'status-excluded' : '';

        let areaDisplay = record.area || '—';
        if (areaDisplay.includes('-')) {
            areaDisplay = areaDisplay.split('-').pop();
        }

        row.innerHTML =
            '<td><input type="checkbox" class="record-checkbox rounded" data-id="' + escHtml(record.id) + '" onchange="updateBatchBar()"></td>' +
            '<td class="hidden">' + escHtml(record.id) + '</td>' +
            '<td><a href="https://www.tianyancha.com/search?key=' + encodeURIComponent(record.name) + '" target="_blank" class="font-medium text-primary-600 dark:text-primary-400 hover:underline">' + escHtml(record.name) + '</a><br><small>' + escHtml((record.address || '').substring(0, 30)) + '...</small></td>' +
            '<td>' + escHtml(areaDisplay) + '</td>' +
            '<td>' + escHtml(record.legal_person || '—') + '</td>' +
            '<td>' + escHtml(record.phone || '—') + '</td>' +
            '<td>' + escHtml(record.registered_capital || '—') + '</td>' +
            '<td>' + escHtml(record.establish_date || '—') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + escHtml(record.status) + '</span></td>' +
            '<td>' +
                '<button class="action-btn btn-view" onclick="viewRecord(\'' + escHtml(record.id) + '\')" title="查看详情">👁️</button>' +
                '<button class="action-btn btn-edit" onclick="editRecord(\'' + escHtml(record.id) + '\')" title="编辑">✏️</button>' +
                '<button class="action-btn btn-delete" onclick="deleteRecord(\'' + escHtml(record.id) + '\')" title="删除">🗑️</button>' +
                '<button class="action-btn btn-exclude" onclick="excludeRecord(\'' + escHtml(record.id) + '\')" title="屏蔽">❌</button>' +
            '</td>';
        tbody.appendChild(row);
    });
}

// 查看详情
function viewRecord(id) {
    fetch('/api/records/' + id)
        .then(r => r.json())
        .then(record => {
            const body = document.getElementById('viewModalBody');
            body.innerHTML = `
                <table class="w-full text-sm">
                    <tr><td class="py-2 pr-4 font-medium text-gray-500 w-24">企业名称</td><td class="py-2">${escHtml(record.name || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">区域</td><td class="py-2">${escHtml(record.area || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">地址</td><td class="py-2">${escHtml(record.address || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">法人</td><td class="py-2">${escHtml(record.legal_person || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">电话</td><td class="py-2">${escHtml(record.phone || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">注册资本</td><td class="py-2">${escHtml(record.registered_capital || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">成立日期</td><td class="py-2">${escHtml(record.establish_date || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">状态</td><td class="py-2">${escHtml(record.status || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">来源</td><td class="py-2">${escHtml(record.source || '—')}</td></tr>
                    <tr><td class="py-2 pr-4 font-medium text-gray-500">备注</td><td class="py-2">${escHtml(record.notes || '—')}</td></tr>
                </table>
            `;
            document.getElementById('viewModal').classList.remove('hidden');
        })
        .catch(err => alert('获取详情失败: ' + err.message));
}

function closeViewModal() {
    document.getElementById('viewModal').classList.add('hidden');
}

// 编辑记录
function editRecord(id) {
    fetch('/api/records/' + id)
        .then(r => r.json())
        .then(record => {
            const fields = {
                'editId': record.id || '',
                'editName': record.name || '',
                'editArea': record.area || '',
                'editAddress': record.address || '',
                'editLegal': record.legal_person || '',
                'editPhone': record.phone || '',
                'editCapital': record.registered_capital || '',
                'editDate': record.establish_date || '',
                'editStatus': record.status || '筹建审批中',
                'editSource': record.source || '天眼查',
                'editNotes': record.notes || ''
            };
            for (const [id, value] of Object.entries(fields)) {
                const el = document.getElementById(id);
                if (el) el.value = value;
            }
            const modal = document.getElementById('editModal');
            if (modal) {
                modal.classList.remove('hidden');
            } else {
                alert('编辑弹窗未加载，请刷新页面重试');
            }
        })
        .catch(err => alert('获取记录失败: ' + err.message));
}

function closeEditModal() {
    document.getElementById('editModal').classList.add('hidden');
}

// 保存编辑
function saveRecord() {
    const id = document.getElementById('editId').value;
    const data = {
        name: document.getElementById('editName').value,
        area: document.getElementById('editArea').value,
        address: document.getElementById('editAddress').value,
        legal_person: document.getElementById('editLegal').value,
        phone: document.getElementById('editPhone').value,
        registered_capital: document.getElementById('editCapital').value,
        establish_date: document.getElementById('editDate').value,
        status: document.getElementById('editStatus').value,
        source: document.getElementById('editSource').value,
        notes: document.getElementById('editNotes').value
    };

    fetch('/api/records/' + id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(res => {
        showToast('保存成功', 'success');
        closeEditModal();
        loadAllRecords();
    })
    .catch(err => showToast('保存失败: ' + err.message, 'error'));
}

// 删除记录
function deleteRecord(id) {
    if (!confirm('确定删除此记录吗？')) return;

    fetch('/api/records/' + id, {method: 'DELETE'})
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                showToast('删除成功', 'success');
                loadAllRecords(); // 重新加载数据
            } else {
                showToast('删除失败: ' + (res.message || '未知错误'), 'error');
            }
        })
        .catch(err => showToast('删除失败: ' + err.message, 'error'));
}

// 排除记录（使用专用端点，单次请求）
function excludeRecord(id) {
    if (!confirm('确定标记为"不是网吧"吗？此记录将被隐藏。')) return;

    fetch('/api/records/' + id + '/exclude', {method: 'POST'})
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                showToast('已标记排除', 'success');
                loadAllRecords(); // 重新加载数据
            } else {
                showToast('操作失败: ' + (res.message || '未知错误'), 'error');
            }
        })
        .catch(err => showToast('操作失败: ' + err.message, 'error'));
}

// 清除所有数据
function clearAllData() {
    if (!confirm('确定清除所有数据吗？此操作不可恢复！')) return;
    if (!confirm('再次确认：确定要删除所有企业数据吗？')) return;

    fetch('/api/records/clear', {method: 'DELETE'})
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                showToast('已清除所有数据', 'success');
                setTimeout(() => location.reload(), 500);
            } else {
                showToast('清除失败: ' + (res.message || '未知错误'), 'error');
            }
        })
        .catch(err => showToast('清除失败: ' + err.message, 'error'));
}

// 导出数据
function exportData() {
    fetch('/api/export')
        .then(r => r.json())
        .then(data => {
            const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '网吧数据_' + new Date().toISOString().split('T')[0] + '.json';
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(err => alert('导出失败: ' + err.message));
}

// 页面加载完成后加载数据
document.addEventListener('DOMContentLoaded', loadAllRecords);

// 监听筛选器变化
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.getElementById('filterArea').addEventListener('change', applyFilters);
    document.getElementById('filterStatus').addEventListener('change', applyFilters);
    document.getElementById('filterTime').addEventListener('change', applyFilters);
});

// ==================== 批量操作 ====================

// 全选/取消全选
function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.record-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
        const row = cb.closest('tr');
        if (row) {
            row.classList.toggle('bg-primary-50', selectAll.checked);
            row.classList.toggle('dark:bg-primary-900/20', selectAll.checked);
        }
    });
    updateBatchBar();
}

// 更新批量操作栏
function updateBatchBar() {
    const count = getSelectedIds().length;
    const batchBar = document.getElementById('batchBar');
    const countEl = document.getElementById('selectedCount');

    if (count > 0) {
        batchBar.classList.remove('hidden');
        countEl.textContent = count;
    } else {
        batchBar.classList.add('hidden');
    }

    // 更新行高亮
    document.querySelectorAll('.record-checkbox').forEach(cb => {
        const row = cb.closest('tr');
        if (row) {
            row.classList.toggle('bg-primary-50', cb.checked);
            row.classList.toggle('dark:bg-primary-900/20', cb.checked);
        }
    });
}

// 获取选中的ID列表
function getSelectedIds() {
    const ids = [];
    document.querySelectorAll('.record-checkbox:checked').forEach(cb => {
        ids.push(cb.dataset.id);
    });
    return ids;
}

// 取消选择
function clearSelection() {
    document.querySelectorAll('.record-checkbox').forEach(cb => {
        cb.checked = false;
        const row = cb.closest('tr');
        if (row) {
            row.classList.remove('bg-primary-50', 'dark:bg-primary-900/20');
        }
    });
    document.getElementById('selectAll').checked = false;
    updateBatchBar();
}

// 批量排除
function batchExclude() {
    const ids = getSelectedIds();
    if (!ids.length) return;
    if (!confirm('确定排除选中的 ' + ids.length + ' 条记录吗？')) return;

    fetch('/api/records/batch/exclude', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids})
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            showToast('已排除 ' + res.updated + ' 条记录', 'success');
            loadAllRecords();
            clearSelection();
        } else {
            showToast('操作失败: ' + (res.error || ''), 'error');
        }
    })
    .catch(err => showToast('操作失败: ' + err.message, 'error'));
}

// 显示批量修改状态弹窗
function showBatchStatusModal() {
    if (!getSelectedIds().length) return;
    document.getElementById('batchStatusModal').classList.remove('hidden');
}

// 关闭批量修改状态弹窗
function closeBatchStatusModal() {
    document.getElementById('batchStatusModal').classList.add('hidden');
}

// 批量修改状态
function batchChangeStatus() {
    const ids = getSelectedIds();
    const status = document.getElementById('batchStatusSelect').value;
    if (!ids.length || !status) return;

    fetch('/api/records/batch/status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids, status: status})
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            showToast('已更新 ' + res.updated + ' 条记录状态为「' + status + '」', 'success');
            closeBatchStatusModal();
            loadAllRecords();
            clearSelection();
        } else {
            showToast('操作失败: ' + (res.error || ''), 'error');
        }
    })
    .catch(err => showToast('操作失败: ' + err.message, 'error'));
}

// 批量删除
function batchDelete() {
    const ids = getSelectedIds();
    if (!ids.length) return;
    if (!confirm('确定删除选中的 ' + ids.length + ' 条记录吗？此操作不可恢复！')) return;

    fetch('/api/records/batch/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids})
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            showToast('已删除 ' + res.deleted + ' 条记录', 'success');
            loadAllRecords();
            clearSelection();
        } else {
            showToast('操作失败: ' + (res.error || ''), 'error');
        }
    })
    .catch(err => showToast('操作失败: ' + err.message, 'error'));
}
