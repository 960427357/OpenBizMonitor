// 全局数据
let allRecords = [];

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
            // 添加最后一级
            areaSet.add(areas[areas.length - 1]);
        }
    });

    const select = document.getElementById('filterArea');
    select.innerHTML = '<option value="">全部区域</option>';
    Array.from(areaSet).sort().forEach(area => {
        select.innerHTML += `<option value="${area}">${area}</option>`;
    });
}

// 应用筛选
function applyFilters() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const filterArea = document.getElementById('filterArea').value;
    const filterStatus = document.getElementById('filterStatus').value;
    const filterTime = parseInt(document.getElementById('filterTime').value) || 0;

    let filtered = allRecords.filter(record => {
        // 搜索文本筛选
        if (query) {
            const searchText = (record.name + ' ' + (record.address || '') + ' ' + (record.legal_person || '')).toLowerCase();
            if (!searchText.includes(query)) return false;
        }

        // 区域筛选
        if (filterArea) {
            const areas = (record.area || '').split('-');
            const areaDisplay = areas[areas.length - 1] || '';
            if (areaDisplay !== filterArea) return false;
        }

        // 状态筛选
        if (filterStatus && record.status !== filterStatus) {
            return false;
        }

        // 时间筛选
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

// 搜索功能
function searchRecords() {
    applyFilters();
}

// 重置筛选
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
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4">没有找到符合条件的记录</td></tr>';
        return;
    }

    records.forEach(record => {
        const row = document.createElement('tr');
        row.dataset.id = record.id;

        const statusClass = record.status === '筹建审批中' ? 'status-pending' :
                           record.status === '已排除' ? 'status-excluded' : '';

        // 区域只显示最后一级
        let areaDisplay = record.area || '—';
        if (areaDisplay.includes('-')) {
            areaDisplay = areaDisplay.split('-').pop();
        }

        row.innerHTML =
            '<td>' + record.id + '</td>' +
            '<td><strong>' + record.name + '</strong><br><small>' + (record.address || '').substring(0, 30) + '...</small></td>' +
            '<td>' + areaDisplay + '</td>' +
            '<td>' + (record.legal_person || '—') + '</td>' +
            '<td>' + (record.registered_capital || '—') + '</td>' +
            '<td>' + (record.establish_date || '—') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + record.status + '</span></td>' +
            '<td>' +
                '<button class="action-btn btn-view" onclick="viewRecord(\'' + record.id + '\')">👁️</button>' +
                '<button class="action-btn btn-edit" onclick="editRecord(\'' + record.id + '\')">✏️</button>' +
                '<button class="action-btn btn-delete" onclick="deleteRecord(\'' + record.id + '\')">🗑️</button>' +
                '<button class="action-btn btn-exclude" onclick="excludeRecord(\'' + record.id + '\')">❌</button>' +
            '</td>';
        tbody.appendChild(row);
    });
}

// 查看详情
function viewRecord(id) {
    fetch('/api/records/' + id)
        .then(r => r.json())
        .then(record => {
            document.getElementById('viewId').textContent = record.id || '—';
            document.getElementById('viewName').textContent = record.name || '—';
            document.getElementById('viewArea').textContent = record.area || '—';
            document.getElementById('viewAddress').textContent = record.address || '—';
            document.getElementById('viewLegal').textContent = record.legal_person || '—';
            document.getElementById('viewCapital').textContent = record.registered_capital || '—';
            document.getElementById('viewDate').textContent = record.establish_date || '—';
            document.getElementById('viewStatus').textContent = record.status || '—';
            document.getElementById('viewSource').textContent = record.source || '—';
            document.getElementById('viewNotes').textContent = record.notes || '—';

            const modal = new bootstrap.Modal(document.getElementById('viewModal'));
            modal.show();
        })
        .catch(err => alert('获取详情失败: ' + err.message));
}

// 编辑记录
function editRecord(id) {
    fetch('/api/records/' + id)
        .then(r => r.json())
        .then(record => {
            // 确保模态框元素存在
            setTimeout(() => {
                const editId = document.getElementById('editId');
                const editName = document.getElementById('editName');
                const editArea = document.getElementById('editArea');
                
                if (!editId || !editName || !editArea) {
                    alert('编辑表单未加载，请刷新页面重试');
                    return;
                }
                
                editId.value = record.id || '';
                editName.value = record.name || '';
                editArea.value = record.area || '';
                document.getElementById('editAddress').value = record.address || '';
                document.getElementById('editLegal').value = record.legal_person || '';
                document.getElementById('editCapital').value = record.registered_capital || '';
                document.getElementById('editDate').value = record.establish_date || '';
                document.getElementById('editStatus').value = record.status || '筹建审批中';
                document.getElementById('editSource').value = record.source || '天眼查';
                document.getElementById('editNotes').value = record.notes || '';

                const modal = new bootstrap.Modal(document.getElementById('editModal'));
                modal.show();
            }, 100);
        })
        .catch(err => alert('获取记录失败: ' + err.message));
}

// 保存编辑
function saveRecord() {
    const id = document.getElementById('editId').value;
    const data = {
        name: document.getElementById('editName').value,
        area: document.getElementById('editArea').value,
        address: document.getElementById('editAddress').value,
        legal_person: document.getElementById('editLegal').value,
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
        alert('保存成功');
        bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
        applyFilters();
    })
    .catch(err => alert('保存失败: ' + err.message));
}

// 删除记录
function deleteRecord(id) {
    if (!confirm('确定删除此记录吗？')) return;

    fetch('/api/records/' + id, {method: 'DELETE'})
        .then(() => {
            alert('删除成功');
            applyFilters();
        })
        .catch(err => alert('删除失败: ' + err.message));
}

// 排除记录
function excludeRecord(id) {
    if (!confirm('确定标记为"不是网吧"吗？此记录将被隐藏。')) return;

    fetch('/api/records/' + id)
        .then(r => r.json())
        .then(record => {
            record.status = '已排除';
            return fetch('/api/records/' + id, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(record)
            });
        })
        .then(() => {
            alert('已标记排除');
            applyFilters();
        })
        .catch(err => alert('操作失败: ' + err.message));
}

// 清除所有数据
function clearAllData() {
    if (!confirm('确定清除所有数据吗？此操作不可恢复！')) return;
    if (!confirm('再次确认：确定要删除所有企业数据吗？')) return;

    fetch('/api/records/clear', {method: 'DELETE'})
        .then(() => {
            alert('已清除所有数据');
            location.reload();
        })
        .catch(err => alert('清除失败: ' + err.message));
}

// 导出数据
function exportData() {
    fetch('/api/export')
        .then(r => r.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '网吧数据_' + new Date().toISOString().split('T')[0] + '.xlsx';
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