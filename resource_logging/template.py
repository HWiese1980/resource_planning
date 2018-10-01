template = """
Hi Elsa, hi Patrick,

meine Ressourcenplanung für $pmonth $pyear und $nmonth $nyear:

**${pmonth} '${pyears}**

$pdata
$psum
    
**${nmonth} '${nyears}**

$ndata
* #### FILL IN: ${rest}% remaining ####
    
Liebe Grüße,

Hendrik
"""

dtemplate = """* $project: $percentage%"""
stemplate = """* **Summe: ${percsum}%**"""
