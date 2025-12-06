document.addEventListener('DOMContentLoaded',function(){
  const status = document.getElementById('statusFilter');
  const quick = document.getElementById('tableFilter');

  function apply(){
    const s = status ? status.value : 'all';
    const q = quick ? quick.value.toLowerCase() : '';
    document.querySelectorAll('#loansTable tbody tr').forEach(row=>{
      const okStatus = s === 'all' || row.dataset.status === s;
      const okText = row.textContent.toLowerCase().includes(q);
      row.style.display = (okStatus && okText) ? '' : 'none';
    });
  }

  status && status.addEventListener('change', apply);
  quick && quick.addEventListener('input', apply);
});
