$(document).ready(function() {
    $("input.filter[type='button']").click(function(){
	var loc = $(location).attr('pathname') + '?';
	$("input.filter:checked").each(function(){
	    loc = loc + $(this).attr('name') + '=' + $(this).attr('value') + '&';
	});
	window.location.pathname=loc;
        return false;
    });
 });
