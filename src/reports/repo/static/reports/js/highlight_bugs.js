$(document).ready(function() {
    
    //highlight color for bugs
    var color = "<span style=\"background-color:yellow\">"
    var bug_container = new Array();
    for (var i=0; i < issue_ref.length; i++)
	bug_container[i] = new Array();

    $('div.changelog').each(function() {
	var line = $(this).html();

	//higlight and add links according to rules
	for (var i=0; i < issue_ref.length; i++) {
	    var re = new RegExp(issue_ref[i].re, "gi");
	    if (matches = line.match(re)) {
		line = line.replace(re, "<a href=\"" + issue_ref[i].url + "/show_bug.cgi?id=$3" + "\">" + color + "$1</span></a>");
		add_to_container(matches, bug_container[i]);
	    }
	}
	$(this).html(line);
    });

    $('div#issues').each(function() {
	body = $(this).html();
	bugs_html = "";
        bugs_link = "";
        bugs_head = "";
	for (var i=0; i < bug_container.length; i++) {
	    if (bug_container[i].length > 0){
		bugs_head = "<b>" + issue_ref[i].name + ":</b> "
		bugs_link += "<a href='" + issue_ref[i].url + "/buglist.cgi?bug_id=";
	        for (var j = 0; j < bug_container[i].length; j++) {
  		    bugs_html += "<a href=\"" + issue_ref[i].url + "/show_bug.cgi?id=" + bug_container[i][j] + "\">" + bug_container[i][j] + ", </a>";
		    bugs_link += bug_container[i][j] + ",";
                }
		bugs_link += "'>(ALL) </a>";
            }
	    bugs_html += "</br>";
            bugs_html = bugs_head + bugs_link + bugs_html;
	}
	$(this).html(bugs_html + body);
    });

    function add_to_container(values, sack){
	for (var i=0; i < values.length; i++) {
	    var bug = values[i];
	    for (var j=0; j < issue_ref.length; j++) {
		re = new RegExp(issue_ref[j].re, "gi")
		if (bug.match(re)){
		    bug = bug.replace(re, "$3");
		}
	    }
	    if (!check_if_exists(bug, sack))
		sack.push(bug);
	}
    }

    function check_if_exists(value, sack){
	for (var i=0; i < sack.length; i++)
	    if (value == sack[i])
		return true;
	return false;
    }

});
